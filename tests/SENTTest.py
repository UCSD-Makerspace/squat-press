import lx3302a.SENTReader.SENTReader as SENTReader
from lx3302a.SENTReader.interpolate import interpolate
import time
import pigpio

# Each tuple is (mechanical_distance_mm, SENT_default_EEPROM)
calibration_table = [
    (0.000, 3723),
    (0.254, 3707),
    (0.508, 3689),
    (0.762, 3666),
    (1.016, 3645),
    (1.270, 3624),
    (1.524, 3601),
    (1.778, 3578),
    (2.032, 3554),
    (2.286, 3533),
    (2.540, 3514),
    (2.794, 3492),
    (3.048, 3472),
    (3.302, 3448),
    (3.556, 3426),
    (3.810, 3402),
    (4.064, 3378),
    (4.318, 3354),
    (4.572, 3333),
    (4.826, 3311),
    (5.080, 3290),
    (5.334, 3269),
    (5.588, 3249),
    (5.842, 3226),
    (6.096, 3206),
    (6.350, 3185),
    (6.604, 3162),
    (6.858, 3141),
    (7.112, 3118),
    (7.366, 3095),
    (7.620, 3072),
    (7.874, 3051),
    (8.128, 3031),
    (8.382, 3008),
    (8.636, 2986),
    (8.890, 2964),
    (9.144, 2941),
    (9.398, 2919),
    (9.652, 2898),
    (9.906, 2876),
    (10.160, 2855),
    (10.414, 2832),
    (10.668, 2812),
    (10.922, 2789),
    (11.176, 2768),
    (11.430, 2746),
    (11.684, 2725),
    (11.938, 2702),
    (12.192, 2681),
    (12.446, 2660),
    (12.700, 2637),
    (12.954, 2617),
    (13.208, 2596),
    (13.462, 2573),
    (13.716, 2553),
    (13.970, 2531),
    (14.224, 2510),
    (14.478, 2490),
    (14.732, 2467),
    (14.986, 2445),
    (15.240, 2422),
    (15.494, 2402),
    (15.748, 2380),
    (16.002, 2357),
    (16.256, 2337),
    (16.510, 2314),
    (16.764, 2293),
    (17.018, 2271),
    (17.272, 2251),
    (17.526, 2228),
    (17.780, 2205),
    (18.034, 2185),
    (18.288, 2165),
    (18.542, 2142),
    (18.796, 2120),
    (19.050, 2097),
    (19.304, 2073),
    (19.558, 2051),
    (19.812, 2032),
    (20.066, 2010),
    (20.320, 1987),
    (20.574, 1966),
    (20.828, 1944),
    (21.082, 1921),
    (21.336, 1898),
    (21.590, 1875),
    (21.844, 1853),
    (22.098, 1830),
    (22.352, 1809),
    (22.606, 1787),
    (22.860, 1764),
    (23.114, 1741),
    (23.368, 1718),
    (23.622, 1695),
    (23.876, 1672),
    (24.130, 1649),
    (24.384, 1621),
    (24.638, 1596),
]

def main():
    SENT_GPIO = 18
    RUN_TIME = 6000000000.0
    SAMPLE_TIME = 0.1

    pi = pigpio.pi()
    p = SENTReader.SENTReader(pi, SENT_GPIO)

    start = time.time()

    most_recent_data = 0
    time_since_last_data = 0
    mechanical_distance = 0
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

        if new_data:
            mechanical_distance = interpolate(most_recent_data, calibration_table)
            if mechanical_distance is None:
                mechanical_distance = 0.0
            # Update filtered_data only when new data
            filtered_data = (filtered_data * alpha) + (most_recent_data * (1-alpha))

        print(
            f"Filtered Data: {filtered_data:.2f}, "
            f"Current Data: {most_recent_data if new_data else 'Old Data'}, "
            f"Depth: {mechanical_distance:.3f} mm"
        )
        
        # print(f"Sent Status= {status}, 12-bit DATA 1= {data1:4.0f}, DATA 2= {data2:4.0f} " +
        #       f", tickTime(uS)= {ticktime:4.0f}, CRC= {crc}, Errors= {errors:4b}, PERIOD = {syncPulse}")

    # stop the thread in SENTReader
    p.stop()
    # clear the pi object instance
    pi.stop()

if __name__ == "__main__":
    main()
