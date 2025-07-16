import lx3302a.SENTReader.SENTReader as SENTReader
import lx3302a.SENTReader.interpolate as interpolate
import time
import pigpio

# Each tuple is (mechanical_distance_mm, SENT_default_EEPROM)
calibration_table = [
    (0, 3675),
    (0.254, 3672),
    (0.508, 3664),
    (0.762, 3656),
    (1.016, 3647),
    (1.27, 3638),
    (1.524, 3630),
    (1.778, 3620),
    (2.032, 3610),
    (2.286, 3600),
    (2.54, 3588),
    (2.794, 3577),
    (3.048, 3565),
    (3.302, 3554),
    (3.556, 3541),
    (3.81, 3527),
    (4.064, 3515),
    (4.318, 3502),
    (4.572, 3488),
    (4.826, 3475),
    (5.08, 3461),
    (5.334, 3448),
    (5.588, 3433),
    (5.842, 3419),
    (6.096, 3407),
    (6.35, 3392),
    (6.604, 3377),
    (6.858, 3362),
    (7.112, 3348),
    (7.366, 3333),
    (7.62, 3319),
    (7.874, 3311),
    (8.128, 3303),
    (8.382, 3294),
    (8.636, 3286),
    (8.89, 3277),
    (9.144, 3269),
    (9.398, 3260),
    (9.652, 3252),
    (9.906, 3242),
    (10.16, 3219),
    (10.414, 3199),
    (10.668, 3180),
    (10.922, 3157),
    (11.176, 3137),
    (11.43, 3115),
    (11.684, 3093),
    (11.938, 3073),
    (12.192, 3052),
    (12.446, 3031),
    (12.7, 3010),
    (12.954, 2991),
    (13.208, 2971),
    (13.462, 2949),
    (13.716, 2929),
    (13.97, 2910),
    (14.224, 2888),
    (14.478, 2875),
    (14.732, 2860),
    (14.986, 2847),
    (15.24, 2833),
    (15.494, 2819),
    (15.748, 2806),
    (16.002, 2793),
    (16.256, 2779),
    (16.51, 2766),
    (16.764, 2752),
    (17.018, 2740),
    (17.272, 2728),
    (17.526, 2714),
    (17.78, 2699),
    (18.034, 2686),
    (18.288, 2674),
    (18.542, 2660),
    (18.796, 2647),
    (19.05, 2634),
    (19.304, 2619),
    (19.558, 2600),
    (19.812, 2585),
    (20.066, 2569),
    (20.32, 2551),
    (20.574, 2535),
    (20.828, 2519),
    (21.082, 2503),
    (21.336, 2485),
    (21.59, 2469),
    (21.844, 2453),
    (22.098, 2435),
    (22.352, 2420),
    (22.606, 2402),
    (22.86, 2384),
    (23.114, 2368),
    (23.368, 2350),
    (23.622, 2333),
    (23.876, 2317),
    (24.13, 2298),
    (24.384, 2282),
    (24.638, 2265)
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
