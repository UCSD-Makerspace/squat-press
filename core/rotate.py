import time
import pigpio
import logging
from tests.config import SystemConfig

import Dispenser.TMC2209.tmc2209 as tmc2209

STEP_DEGREES = 360 / 8 # 8 total steps for 1 revolution (8 holes in the pellet wheel)
MAX_ROTATION = 45 * 5 # 45 degrees per hole; jitter if after 5 rotations pellet is not dispensed
ROTATE_COOLDOWN = 1.0 # 1 second cooldown between rotations
JITTER_DEGREES = 20
JITTER_AMOUNT = 8

def rotate_step(motor, step_degrees, ltc) -> bool:
    if motor is None:
        logging.error("Motor not initialized, cannot rotate")
        return False
    
    try:
        thread, waiting_thread = motor.rotate_degrees_threaded(step_degrees, 0)

        while thread.is_alive():
            ltc.update()
            if ltc.get_detected():
                logging.info("Pellet detected during rotation, stopping motor")
                motor.stop()
                thread.join(timeout=2.0)
                waiting_thread.join(timeout=1.0)
                return False
            time.sleep(0.05)

        waiting_thread.join()
        return True
    except Exception as e:
        logging.error(f"Failed to rotate: {e}")
        motor.stop()
        return False
    
def dispense(motor, ltc) -> bool:
    TOTAL_ROTATED = 0

    if motor is None:
        logging.error("Motor not intitialized for dispensing")
        return False
    
    while TOTAL_ROTATED < MAX_ROTATION:
        ltc.update()
        if ltc.get_detected():
            logging.info("Pellet detected during dispense, stopping rotation")
            motor.stop()
            time.sleep(0.1)
            return True
        
        if not rotate_step(motor, STEP_DEGREES, ltc):
            return False

        TOTAL_ROTATED += STEP_DEGREES
        time.sleep(ROTATE_COOLDOWN)

    logging.info("Failed to dispense pellet after 5 rotations, jittering...")
    return jitter(motor, JITTER_DEGREES, JITTER_AMOUNT)

def jitter(motor, jitter_degrees, jitter_amount) -> bool:
    if motor is None:
        logging.error("Motor not intialized, failed to jitter")
        return False
    try:
        direction = 1
        for _ in range(jitter_amount):
            step = jitter_degrees * direction
            thread, _ = motor.rotate_degrees_threaded(step, 0)
            direction *= -1
            print(f"Jittering {jitter_degrees} degrees...")
            thread.join()
        return True
    except Exception as e:
        logging.error(f"Failed to jitter motor: error {e}")
        return False