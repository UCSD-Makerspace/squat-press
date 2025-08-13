import time
import pigpio
import logging
from tests.config import SystemConfig

import Dispenser.TMC2209.tmc2209 as tmc2209

STEP_DEGREES = 360 / 8 # 8 total steps for 1 revolution (8 holes in the pellet wheel)
MAX_ROTATION = 45 * 5 # 45 degrees per hole; jitter if after 5 rotations pellet is not dispensed
ROTATE_COOLDOWN = 1.0 # 1 second cooldown between rotations
JITTER_DEGREES = 15
JITTER_AMOUNT = 5

def rotate_step(motor, step_degrees) -> bool:
    if motor is None:
        logging.error("Motor not initialized, cannot rotate")
        return False
    
    try:
        thread, _ = motor.rotate_degrees_threaded(step_degrees, 0)
        thread.join()
        return True
    except Exception as e:
        logging.error(f"Failed to rotate: {e}")
        return False
    
def dispense(motor):
    TOTAL_ROTATED = 0
    if motor is None:
        logging.error("Motor not intitialized for dispensing")
        return False
    while TOTAL_ROTATED < MAX_ROTATION:
        rotate_step(motor, STEP_DEGREES)
        time.sleep(ROTATE_COOLDOWN)
        TOTAL_ROTATED += STEP_DEGREES
        if TOTAL_ROTATED >= MAX_ROTATION:
            logging.info("Failed to dispense pellet after 5 rotations, jittering...")
            jitter(motor, JITTER_DEGREES, JITTER_AMOUNT)

def jitter(motor, jitter_degrees, jitter_amount):
    DIR = 1
    if motor is None:
        logging.error("Motor not intialized, failed to jitter")
    try:
        for _ in range(jitter_amount):
            jitter_degrees *= DIR
            thread, _ = motor.rotate_degrees_treaded(jitter_degrees, 0)
            DIR = -DIR
            print(f"Jittering {jitter_degrees} degrees...")
            thread.join()
    except Exception as e:
        logging.error(f"Failed to jitter motor: error {e}")
        return False
    
