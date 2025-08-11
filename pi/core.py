import lx3302a.SENTReader.SENTReader as SENTReader
import time
import pigpio
import threading
from os import path
from tests.config import SystemConfig
from time import sleep
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import ADC.ADC as ADC

#### Consts ####
SENT_GPIO = 18

# Core loop for hardware communication #
def main():
    pi = pigpio.pi()
    p = SENTReader.SENTReader(pi, SENT_GPIO)

    # Needed functions
    motor.rotate()
    
    pellet.dispense()
    

    beambreak.record_event()

if __name__ == "__main__":
    
    main()