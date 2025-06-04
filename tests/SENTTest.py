import lx3302a.SENTReader.SENTReader as SENTReader
import time
import pigpio

def main():
    SENT_GPIO = 18
    RUN_TIME = 6000000000.0
    SAMPLE_TIME = 0.1

    pi = pigpio.pi()

    p = SENTReader.SENTReader(pi, SENT_GPIO)

    start = time.time()

    most_recent_data = 0
    time_since_last_data = 0
    filtered_data = 0
    alpha = 0.6
    while (time.time() - start) < RUN_TIME:

        time.sleep(SAMPLE_TIME)
        new_data = False
        status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()
        if errors == 0 or errors == 8:
            most_recent_data = data1
            new_data = True
            time_since_last_data = 0
        else:
            time_since_last_data += SAMPLE_TIME
            if time_since_last_data > 5.0:
                print("No valid data received for 5 seconds, restarting SENTReader")
                p.stop()
                p = SENTReader.SENTReader(pi, SENT_GPIO)
                time.sleep(3.0)
                time_since_last_data = 0
                continue

        print(f"Filtered Data, {filtered_data:0.5f}, Current Data, {(most_recent_data if new_data else 'Old Data')}")
        filtered_data = (filtered_data * alpha) + (most_recent_data * (1-alpha))

        # print(f"Sent Status= {status}, 12-bit DATA 1= {data1:4.0f}, DATA 2= {data2:4.0f} " +
        #       f", tickTime(uS)= {ticktime:4.0f}, CRC= {crc}, Errors= {errors:4b}, PERIOD = {syncPulse}")

    # stop the thread in SENTReader
    p.stop()
    # clear the pi object instance
    pi.stop()

if __name__ == "__main__":
    main()
