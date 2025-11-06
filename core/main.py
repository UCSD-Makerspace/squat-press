import queue

import ADC.ADC as ADC
import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader

from core.threads.dispenser_thread import DispenserThread
from core.threads.linear_sensor_thread import LinearSensorThread
from core.threads.ltc_thread import LTCThread
from event_manager import EventManager

### Helper method imports ###
from loop_helpers import init_hardware, init_pi, check_all_hardware, check_mm_value

def main():
    pi, linear_sensor, motor = None, None, None

    pi = init_pi()
    linear_sensor, LTC, motor = init_hardware(pi)
    check_all_hardware(pi, LTC, motor)

    event_queue = queue.Queue()
    linear_thread = LinearSensorThread(linear_sensor, event_queue, threshold=10)
    ltc_thread = LTCThread(LTC, event_queue)
    dispenser_thread = DispenserThread(motor, event_queue)

    linear_thread.start()
    ltc_thread.start()
    dispenser_thread.start()

    # Main controller
    manager = EventManager(event_queue, dispenser_thread)
    manager.run()

if __name__ == "__main__":
    main()