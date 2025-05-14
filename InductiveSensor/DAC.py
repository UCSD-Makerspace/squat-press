import pigpio
import time

pi = pigpio.pi()

class DAC:
    def __init__(self, pi=None, clk=1_600_000) -> None:
        if pi is None:
            self.pi = pigpio.pi()
        else:
            self.pi = pi
        self.clk = clk
        self.raw_data: bytearray = bytearray(2) # 12-bit = 1.5 bytes
        self.data = 0

    def read(self) -> bytearray:
        spi = pi.spi_open(0, self.clk, 0)  # SPI mode 0 = 0, 0
        _, data_1 = pi.spi_read(spi, 2)  
        # data = ((data_1[0] & 0x1F) << 7) + ((data_1[1] & 0xFE) >> 1)
        pi.spi_close(spi)
        self.raw_data = data_1
        self.data = int.from_bytes(data_1, byteorder="big")
        return data_1

    def get_data(self) -> int:
        return self.data

    def get_raw_data(self) -> bytearray:
        return self.raw_data

if __name__ == "__main__":
    reader = DAC(pi)
    while True:
        print(f"Data: {reader.get_data():0.5f}, Raw Data: {reader.get_raw_data()}")
        time.sleep(0.05) 
