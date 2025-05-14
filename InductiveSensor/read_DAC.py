import pigpio
import time

pi = pigpio.pi()

def read_spi():
    spi = pi.spi_open(0, 1_600_000, 0)  # SPI mode 0 = 0, 0
    _, data_1 = pi.spi_read(spi, 2)  
    # data = ((data_1[0] & 0x1F) << 7) + ((data_1[1] & 0xFE) >> 1)
    pi.spi_close(spi)
    return data_1

def bytearr_to_int(bytearr):
    return int.from_bytes(bytearr, byteorder='big')

while True:
    print(f"Data: {bytearr_to_int(read_spi())}")
    time.sleep(0.05) 
