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
        print(f"Sent Status= {status}, 12-bit DATA 1= {data1:4.0f}, DATA 2= {data2:4.0f} " +
              f", tickTime(uS)= {ticktime:4.0f}, CRC= {crc}, Errors= {errors:4b}, PERIOD = {syncPulse}")

    # stop the thread in SENTReader
    p.stop()
    # clear the pi object instance
    pi.stop()

if __name__ == "__main__":
    main()