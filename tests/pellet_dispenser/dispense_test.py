from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
from core.rotate import dispense
import Dispenser.TMC2209.tmc2209 as tmc2209
import logging
import time
import pigpio

STEP_DEGREES = 360 / 8 # 8 total steps for 1 revolution (8 holes in the pellet wheel)
MAX_ROTATION = 45 * 9 # 45 degrees per rotation; jitter if after 9 rotations pellet is not found
ROTATE_COOLDOWN = 1.0 # 1 second cooldown between rotations
JITTER_DEGREES = 20
JITTER_AMOUNT = 8

def rotate_step(motor, step_degrees, ltc) -> bool:
    try:
        thread, waiting_thread = motor.rotate_degrees_threaded(step_degrees, 0)

        while thread.is_alive():
            ltc.update()
            if ltc.get_detected():
                logging.info("Pellet detected during rotation, stopping motor")
                thread.join(timeout=2.0)
                waiting_thread.join(timeout=1.0)
                motor.stop()
                return True       
        return False
    
    except Exception as e:
        logging.error(f"Failed to rotate motor: {e}")
        motor.stop()
        return False
    
def dispense(motor, ltc) -> bool:
    if motor is None or ltc is None:
        logging.error("Motor or LTC not intitialized for dispense method")
        return False
    
    TOTAL_ROTATED = 0

    while not rotate_step(motor, STEP_DEGREES, ltc):
        ltc.update()
        rotate_step(motor, STEP_DEGREES, ltc)
        TOTAL_ROTATED += STEP_DEGREES
        time.sleep(ROTATE_COOLDOWN)

        if TOTAL_ROTATED >= MAX_ROTATION:
            logging.info("Failed to dispense pellet after 5 rotations, jittering...")
            jitter(motor, JITTER_DEGREES, JITTER_AMOUNT)
            TOTAL_ROTATED = 0
            time.sleep(ROTATE_COOLDOWN)

    motor.stop()
    return True

def jitter(motor, jitter_degrees, jitter_amount):
    try:
        direction = 1
        for _ in range(jitter_amount):
            step = jitter_degrees * direction
            thread, _ = motor.rotate_degrees_threaded(step, 0)
            direction *= -1
            print(f"Jittering {jitter_degrees} degrees...")
            thread.join()
    except Exception as e:
        logging.error(f"Failed to jitter motor: error {e}")

def init_hardware(pi):
    logging.info("Initializing photo interruptor...")
    LTC = PhotoInterruptor(pi)
    
    logging.info("Initializing motor...")
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    
    return LTC, motor

def cleanup_hardware(motor, pi):
    try:
        if motor:
            motor.stop()
        if pi:
            pi.stop()
        logging.info("Hardware cleanup completed")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

def main():
    RUN_TIME = 60 * 5
    dispensed = 0
    dispense_interval = 30.0

    pi = pigpio.pi()
    LTC, motor = init_hardware(pi)

    start_global = time.time()
    while time.time() - start_global < RUN_TIME:
        cycle_start = time.time()

    success = dispense(motor, LTC)
    if success:
        dispensed += 1
        logging.info(f"Successfully dispensed pellet! Total dispensed: {dispensed}")
    else:
        logging.error("Failed to dispense pellet")

    elapsed = time.time() - cycle_start
    remaining_time = dispense_interval - elapsed
    if remaining_time > 0:
        logging.info(f"Waiting {remaining_time:.2f} seconds until next dispense...")
        time.sleep(remaining_time)