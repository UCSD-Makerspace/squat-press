def interpolate(SENT: int, calibration_table) -> float:
    """
    Interpolates inputted SENT value based on predefined calibration table
    to find corresponding mechanical distance.
    """

    # Edit if default EEPROM values are different from these SENT values.
    SENT_MAX, SENT_MIN = 3690, 2240

    if SENT > SENT_MAX or SENT < SENT_MIN:
        raise ValueError("Sent value out of range. Check induction sensor setup.")
    
    # Interpolation formula: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    for i in range(len(calibration_table) - 1):
        dist1, sent1 = calibration_table[i]
        dist2, sent2 = calibration_table[i + 1]

        if sent2 <= SENT <= sent1:
            divisor = (SENT - sent1) / (sent2 - sent1)
            interpolated_distance = dist1 + divisor * (dist2 - dist1)  
            return interpolated_distance
    
    # Example calcuation: We input 3670. 3664 < 3670 < 3672
    # We find the two points (3664, 0.508) and (3672, 0.254)
    # Then calculate divisor = (3670 - 3664) / (3672 - 3664) = 6 / 8 = 0.75
    # Then interpolated_distance = 0.508 + (0.75 * (0.254 - 0.508)) = 0.508 + (-0.1905) = 0.3175

    raise RuntimeError("Failed to interpolate SENT value given calibration table. Check input values.")

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
