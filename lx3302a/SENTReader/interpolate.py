def interpolate(SENT: int, calibration_table) -> float:
    """
    Interpolates inputted SENT value based on predefined calibration table
    to find corresponding mechanical distance.
    """
    SENT_MAX, SENT_MIN = 4000, 2000

    if SENT > SENT_MAX or SENT < SENT_MIN:
        print(f"SENT value {SENT} out of sensor range [{SENT_MIN}-{SENT_MAX}].")
        # Clamp to min/max of calibration table
        if SENT > calibration_table[0][1]:  # Above highest calibrated SENT
            return calibration_table[0][0]
        if SENT < calibration_table[-1][1]:  # Below lowest calibrated SENT
            return calibration_table[-1][0]

    for i in range(len(calibration_table) - 1):
        dist1, sent1 = calibration_table[i]
        dist2, sent2 = calibration_table[i + 1]

        if sent2 <= SENT <= sent1:
            divisor = (SENT - sent1) / (sent2 - sent1)
            interpolated_distance = dist1 + divisor * (dist2 - dist1)  
            return interpolated_distance

    print(f"SENT value {SENT} not within calibration table interpolation range.")
    return None
