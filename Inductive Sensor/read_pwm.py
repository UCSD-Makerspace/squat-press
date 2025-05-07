import pigpio

pi = pigpio.pi()

def read_spi():
    spi = pi.spi_open(0, 1_600_000, 0)  # SPI mode 0 = 0, 0
    _, data_1 = pi.spi_read(spi, 2)  
    data = ((data_1[0] & 0x1F) << 7) + ((data_1[1] & 0xFE) >> 1)
    pi.spi_close(spi)
    return data

while True:
    print(f"Data: {read_spi()}")
    pi.sleep(0.1)  # Sleep for 100ms to avoid flooding the SPI bus
