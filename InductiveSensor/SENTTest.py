import SENTReader
import time
import pigpio

def main():
    SENT_GPIO = 18
    RUN_TIME = 6000000000.0
    SAMPLE_TIME = 0.1

    pi = pigpio.pi()

    p = SENTReader.SENTReader(pi, SENT_GPIO)

    start = time.time()

    while (time.time() - start) < RUN_TIME:

        time.sleep(SAMPLE_TIME)

        status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()
        print("Sent Status= %s - 12-bit DATA 1= %4.0f - DATA 2= %4.0f - tickTime(uS)= %4.2f - CRC= %s - Errors= %s - PERIOD = %s" % (status,data1,data2,ticktime,crc,errors,syncPulse))
        print("Sent Stat2s= %s - 12-bit DATA 1= %4.0f - DATA 2= %4.0f - tickTime(uS)= %4.2f - CRC= %s - Errors= %s - PERIOD = %s" % (p.statusNibble(),p.dataField1(),p.dataField2(),p.tick(),p.crcNibble(),p.errorFrame(),p.syncPulse()))

    # stop the thread in SENTReader
    p.stop()
    # clear the pi object instance
    pi.stop()

if __name__ == "__main__":
    main()