def interpolate(SENT: int, calibration_table) -> float:
    """
    Interpolates inputted SENT value based on predefined calibration table
    to find corresponding mechanical distance.
    """

    # Edit if default EEPROM values are different from these SENT values.
    SENT_MAX, SENT_MIN = 4000, 2000

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

    #raise RuntimeError("Failed to interpolate SENT value given calibration table. Check input values.")
    print(f"SENT value not within range of table: {SENT}")