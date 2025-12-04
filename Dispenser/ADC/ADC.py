import pigpio
import time

MAX_VAL = 2**13 - 1

class ADC:
    def __init__(self, pi=None, clk=1_600_000) -> None:
        if pi is None:
            self.pi = pigpio.pi()
        else:
            self.pi = pi
        self.clk = clk
        self._raw_data: bytearray = bytearray(2) # 12-bit = 1.5 bytes
        self._data = 0

    def update(self) -> bytearray:
        spi = self.pi.spi_open(0, self.clk, 0)  # SPI mode 0 = 0, 0
        _, data_1 = self.pi.spi_read(spi, 2)  
        # data = ((data_1[0] & 0x1F) << 7) + ((data_1[1] & 0xFE) >> 1)
        self.pi.spi_close(spi)
        self._raw_data = data_1
        self._data = int.from_bytes(data_1, byteorder="big")
        return data_1
    
    def get_data(self) -> int:
        return self._data
    
    def get_data_percent(self) -> float:
        return self._data / (MAX_VAL)

    def get_raw_data(self) -> bytearray:
        return self._raw_data

if __name__ == "__main__":
    reader = ADC()
    while True:
        reader.update()
        print(f"Data: {reader.get_data_percent():0.5f}")
        time.sleep(0.05) 
