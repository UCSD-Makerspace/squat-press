from tests.config import SystemConfig
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

### Hardware imports ###
import ADC.ADC as ADC
import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader

### Threads and EventManager ###
from threads.dispenser_thread import DispenserThread
from threads.linear_sensor_thread import LinearSensorThread
from threads.ltc_thread import LTCThread

### Helper method imports ###
from loop_helpers import init_hardware, init_pi, check_all_hardware, check_mm_value

def main():
    pi, p, motor = None, None, None

    pi = init_pi()
    p, LTC, motor = init_hardware(pi)
    check_all_hardware(pi, LTC, motor)

    event_queue = queue.Queue()

    # Threads
    linear_thread = LinearSensorThread(linear_sensor, event_queue, threshold=10)
    ltc_thread = LTCThread(ltc, event_queue)
    dispenser = DispenserThread(motor, event_queue)

    linear_thread.start()
    ltc_thread.start()

    # Main controller
    manager = EventManager(event_queue, dispenser)
    manager.run()

if __name__ == "__main__":
    main()