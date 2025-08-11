import lx3302a.SENTReader.SENTReader as SENTReader
import time
import pigpio
import threading
from os import path
from tests.config import SystemConfig
from tests.IntegrationTest import test_linear_sensor, test_photo_interruptor, test_motor
from time import sleep
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import ADC.ADC as ADC

#### Consts ####
SENT_GPIO = 18

def dispense_pellet(motor):
    logging.info("Lift detected: dispensing pellet.")
    dir = 1
    dist = dir * 180
    thread, _ = motor.rotate_degrees_threaded(dist, 0)
    thread.join()

def init_hardware(pi, config):
    try:
        p = SENTReader.SENTReader(pi, config.SENT_GPIO)

        LTC = PhotoInterruptor(pi)

        motor = tmc2209.TMC2209()
        motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
        return p, LTC, motor
    except Exception as e:
        logging.error(f"Failed to initialize hardware components: {e}")
        return None, None, None

# Core loop for hardware communication #
def main():
    config = SystemConfig()
    pi = pigpio.pi()

    p, LTC, motor = init_hardware(pi, config)
    if not all([p, LTC, motor]):
        logging.error("Hardware initialization failed. Exiting.")
        return
    
    last_state = LTC.get_detected()
    start = time.time()

    while time.time() - start < config.RUN_TIME:
        time.sleep(0.1)
        LTC.update()
        cur_state = LTC.get_detected()
        if last_state is False and cur_state is True:
            dispense_pellet(motor)
            print(f"Pellet dispensed: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
        if last_state is True and cur_state is False:
            print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
            dispense_pellet(motor)

        last_state = cur_state
    
    p.stop()

if __name__ == "__main__":
    main()