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
TEST_LINEAR_SENSOR = False
TEST_PHOTO_INTERRUPTOR = True
TEST_MOTOR = True

def dispense_pellet():
    logging.info("Lift detected: dispensing pellet.")

# Core loop for hardware communication #
def main():
    config = SystemConfig()
    pi = pigpio.pi()
    p = SENTReader.SENTReader(pi, SENT_GPIO)

    threads = []

    try:
        if TEST_LINEAR_SENSOR:
            thread = threading.Thread(target=test_linear_sensor, args=(pi, config))
            threads.append(thread)
            thread.start()
        if TEST_PHOTO_INTERRUPTOR:
            thread = threading.Thread(target=test_photo_interruptor, args=(pi, config))
            threads.append(thread)
            thread.start()
        if TEST_MOTOR:
            thread = threading.Thread(target=test_motor, args=())
            threads.append(thread)
            thread.start()
            
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logging.info("Tests interrupted by user.")
    finally:
        pi.stop()
        logging.info("Tests completed. Cleaning up...")

if __name__ == "__main__":
    main()