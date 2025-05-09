import time
import gpiod
import threading
import pigpio
from enum import Enum
from typing import Tuple

class Fault(Enum):
    NONE = 0
    SYNC_TOO_LONG = 1
    NIBBLE_TOO_LARGE = 2
    NIBBLE_ZERO = 3
    CRC_ERROR = 4
    DATA_NOT_EQUAL = 5

class FaultStatus(int):
    def __init__(self, value: int=0):
        super().__init__()
    
    def setFault(self, fault: Fault):
        """
        Set the status to include a specific fault.
        :param fault: The fault to set.
        """
        if fault == Fault.NONE:
            return FaultStatus(0)
        else:
            return FaultStatus(self | (1 << (fault.value-1)))

    def getFault(self, fault: Fault) -> bool:
        """
        Check if the status has a specific fault.
        :param fault: The fault to check for.
        :return: True if the fault is present, False otherwise.
        """
        if fault == Fault.NONE:
            return self == 0
        return bool(self & (1 << (fault.value-1)))

    def __bool__(self):
        return not self == 0
    
    def __repr__(self):
        return self


class SENTReader:
    """
    A class to read short Format SENT frames
          (see the LX3302A datasheet for a SENT reference from Microchip)
          (also using sent transmission mode where )
          from wikiPedia: The SAE J2716 SENT (Single Edge Nibble Transmission) protocol
               is a point-to-point scheme for transmitting signal values
               from a sensor to a controller. It is intended to allow for
               transmission of high resolution data with a low system cost.

    Short sensor format:
      The first is the SYNC pulse (56 ticks)
      first Nibble : Status (4 bits)
      2nd NIbble   : DAta1 (4 bits)
      3nd Nibble   : Data2 (4 bits)
      4th Nibble   : Data3 (4 bits)
      5th Nibble   : Data1 (4 bits)
      6th Nibble   : Data2 (4 bits)
      7th Nibble   : Data3 (4 bits)
      8th Nibble   : CRC   (4 bits)
    """

    def __init__(self, pi, gpio, Mode=0):
        """
        Instantiate with the Pi and gpio of the SENT signal
        to monitor.
        SENT mode = A0: Microchip LX3302A where the two 12 bit data values are identical.  there are other modes

        """
        self.pi = pi
        self.gpio = gpio
        self.SENTMode = Mode

        # the time that pulse goes high
        self._high_tick = 0
        # the period of the low tick
        self._low_tick = 0
        # the period of the pulse (total data)
        self._period = 0
        # the time the item was low during the period
        self._low = 0
        # the time the output was high during the period
        self._high = 0
        # setting initial value to 100
        self.syncTick = 100

        # keep track of the periods
        self.syncWidth = 0
        self.status = 0
        self.data1 = 0
        self.data2 = 0
        self.data3 = 0
        self.data4 = 0
        self.data5 = 0
        self.data6 = 0
        self.crc = 0
        # initize the sent frame .  Need to use hex for data
        # self.frame = [0,0,0,'0x0','0x0','0x0','0x0','0x0','0x0',0]
        self.frame = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.syncFound = False
        self.frameComplete = False
        self.nibble = 0
        self.numberFrames = 0
        self.SampleStopped = False

        self.pi.set_mode(gpio, pigpio.INPUT)

        # self._cb = pi.callback(gpio, pigpio.EITHER_EDGE, self._cbf)
        # sleep enougth to start reading SENT
        # time.sleep(0.05)
        self.ThreadStop = False
        # start thread to sample the SENT property
        # this is needed for piGPIO sample of 1us and sensing the 3us
        self.OutputSampleThread = threading.Thread(target=self.SampleCallBack)
        self.OutputSampleThread.daemon = True
        self.OutputSampleThread.start()

        # give time for thread to start capturing data
        time.sleep(0.05)

    def SampleCallBack(self):

        # this will run in a loop and sample the SENT path
        # this sampling is required when 1us sample rate for SENT 3us tick time
        while self.ThreadStop == False:

            self.SampleStopped = False
            self._cb = self.pi.callback(self.gpio, pigpio.EITHER_EDGE, self._cbf)
            # wait until sample stopped
            while self.SampleStopped == False:
                # do nothing
                time.sleep(0.001)

            # gives the callback time to cancel so we can start again.
            time.sleep(0.20)

    def _cbf(self, gpio, level, tick):
        # depending on the system state set the tick times.
        # first look for sync pulse. this is found when duty ratio >90
        # print(pgio)
        # print("inside _cpf")
        # print(tick)
        if self.syncFound == False:
            if level == 1:
                self._high_tick = tick
                self._low = pigpio.tickDiff(self._low_tick, tick)
            elif level == 0:
                # this may be a syncpulse if the duty is 51/56
                self._period = pigpio.tickDiff(self._low_tick, tick)
                # not reset the self._low_tick
                self._low_tick = tick
                self._high = pigpio.tickDiff(self._high_tick, tick)
                # sync pulse is detected by finding duty ratio. 51/56
                # but also filter if period is > 90us*56 = 5040
                if (100 * self._high / self._period) > 87 and (self._period < 5100):
                    self.syncFound = True
                    self.syncWidth = self._high
                    self.syncPeriod = self._period
                    # self.syncTick = round(self.syncPeriod/56.0,2)
                    self.syncTick = self.syncPeriod
                    # reset the nibble to zero
                    self.nibble = 0
                    self.SampleStopped = False
        else:
            # now look for the nibble information for each nibble (8 Nibbles)
            if level == 1:
                self._high_tick = tick
                self._low = pigpio.tickDiff(self._low_tick, tick)
            elif level == 0:
                # This will be a data nibble
                self._period = pigpio.tickDiff(self._low_tick, tick)
                # not reset the self._low_tick
                self._low_tick = tick
                self._high = pigpio.tickDiff(self._high_tick, tick)
                self.nibble = self.nibble + 1
                if self.nibble == 1:
                    self.status = self._period
                elif self.nibble == 2:
                    # self.data1 =  hex(int(round(self._period / self.syncTick)-12))
                    self.data1 = self._period
                elif self.nibble == 3:
                    self.data2 = self._period
                elif self.nibble == 4:
                    self.data3 = self._period
                elif self.nibble == 5:
                    self.data4 = self._period
                elif self.nibble == 6:
                    self.data5 = self._period
                elif self.nibble == 7:
                    self.data6 = self._period
                elif self.nibble == 8:
                    self.crc = self._period
                    # now send all to the SENT Frame
                    self.frame = [
                        self.syncPeriod,
                        self.syncTick,
                        self.status,
                        self.data1,
                        self.data2,
                        self.data3,
                        self.data4,
                        self.data5,
                        self.data6,
                        self.crc,
                    ]
                    self.syncFound = False
                    self.nibble = 0
                    self.numberFrames += 1
                    if self.numberFrames > 2:
                        self.cancel()
                        self.SampleStopped = True
                        self.numberFrames = 0

    def ConvertData(self, tickdata, tickTime):
        if tickdata == 0:
            t = "0x0"
        else:
            t = hex(int(round(tickdata / tickTime) - 12))
            if t[0] == "-":
                t = "0x0"
        return t

    def SENTData(self) -> Tuple[str, int, int, str, int, FaultStatus, float]:
        # check that data1 = Data2 if they are not equal return fault = True
        # will check the CRC code for faults.  if fault, return = true
        # returns status, data1, data2, crc, fault
        # self._cb = self.pi.callback(self.gpio, pigpio.EITHER_EDGE, self._cbf)
        # time.sleep(0.1)
        errStatus = FaultStatus(0)
        SentFrame = self.frame[:]
        SENTTick = round(SentFrame[1] / 56.0, 2)

        # the greatest SYNC sync is 90us.   So trip a fault if this occurs
        if SENTTick > 90:
            errStatus = errStatus.setFault(Fault.SYNC_TOO_LONG)

        # convert SentFrame to HEX Format including the status and Crc bits
        for x in range(2, 10):
            SentFrame[x] = self.ConvertData(SentFrame[x], SENTTick)

        SENTCrc = SentFrame[9]
        SENTStatus = SentFrame[2]
        SENTPeriod = SentFrame[0]

        # combine the datafield nibbles
        # [2:] is to remove 0x
        datanibble = "0x" + "".join([str((SentFrame[x]))[2:] for x in range(3, 6)])  
        datanibble2 = "0x" + "".join([str((SentFrame[x]))[2:] for x in range(3, 6)])

        # if using SENT mode 0, then data nibbles should be equal
        if self.SENTMode == 0 and datanibble != datanibble2:
            errStatus = errStatus.setFault(Fault.DATA_NOT_EQUAL)
        
        # Check if data is zero
        if (int(datanibble, 16) == 0) or (int(datanibble2, 16) == 0):
            errStatus = errStatus.setFault(Fault.NIBBLE_ZERO)
        
        # Check if data is too large (> 4096)
        if (int(datanibble, 16) > 0xFFF) or (int(datanibble2, 16) > 0xFFF):
            errStatus = errStatus.setFault(Fault.NIBBLE_TOO_LARGE)
        
        # CRC checking
        # converting the datanibble values to a binary bit string.
        # remove the 0x and 0b from the string
        # Should be 24 bits long
        InputBitString = bin(int((datanibble + datanibble2[2:]), 16))[2:]
        
        # format is set to remove the leading 0b,  4 characters long
        crcBitValue = format(int(str(SENTCrc), 16), "04b")

        # checking the crcValue
        # polybitstring is x^6 + x^4 + x^3 + 1 = 1011001
        # seed is 010101 (input is padded by 000000, but 0^seed immediately overwrites this)
        if self.crcCheck(InputBitString, "1011001", "010101", crcBitValue) == False:
            print("Fault: CRC Error")
            errStatus = errStatus.setFault(Fault.CRC_ERROR)

        # converter to decimnal
        returnData = int(datanibble, 16)
        returnData2 = int(datanibble2, 16)
        # returns both Data values and if there is a FAULT
        return (
            SENTStatus,
            returnData,
            returnData2,
            SENTTick,
            SENTCrc,
            errStatus,
            SENTPeriod,
        )

    def tick(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return ticktime

    def crcNibble(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return crc

    def dataField1(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return data1

    def dataField2(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return data2

    def statusNibble(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return status

    def syncPulse(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return syncPulse

    def errorFrame(self):
        status, data1, data2, ticktime, crc, errors, syncPulse = self.SENTData()
        return errors

    def cancel(self):
        self._cb.cancel()

    def stop(self):
        self.ThreadStop == True

    def crcCheck(self, InputBitString, PolyBitString, seed, crcValue):
        checkOK = False

        PolyBitString = PolyBitString.lstrip("0")           # Remove leading zeros from polynomial
        LenInput = len(InputBitString)
        InputPaddedArray = list(InputBitString + seed)  # Pad with seed value
        while "1" in InputPaddedArray[:LenInput]:
            cur_shift = InputPaddedArray.index("1")
            for i in range(len(PolyBitString)):
                # XOR each bit of the polynomial with the input
                InputPaddedArray[cur_shift + i] = str(
                    int(PolyBitString[i] != InputPaddedArray[cur_shift + i])
                )

        print(f"{InputPaddedArray[LenInput:]}, {crcValue}")
        if InputPaddedArray[LenInput:] == list(crcValue):
            checkOK = True

        return checkOK
