import pigpio
import time

pi = pigpio.pi()

class DAC:
    def __init__(self, pi=None, clk=1_600_000, channel=0):
        if pi is None:
            self.pi = pigpio.pi()
        else:
            self.pi = pi
        self.channel = channel
        self.clk = clk
        self.raw_data = 0

    def read(self):
        spi = pi.spi_open(self.channel, self.clk, 0)  # SPI mode 0 = 0, 0
        _, data_1 = pi.spi_read(spi, 2)  
        # data = ((data_1[0] & 0x1F) << 7) + ((data_1[1] & 0xFE) >> 1)
        pi.spi_close(spi)
        return data_1
    
    def get_data(self):
        return self.raw_data

    @classmethod
    def bytearr_to_int(bytearr):
        return int.from_bytes(bytearr, byteorder='big')

if __name__ == "__main__":
    reader = DAC(pi, 0)
    while True:
        print(f"Data: {DAC.bytearr_to_int(reader.read())}")
        time.sleep(0.05) 
