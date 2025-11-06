import logging
import pigpio
import queue

import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import lx3302a.SENTReader.serial_reader as serial_reader

from core.threads.dispenser_thread import DispenserThread
from core.threads.linear_sensor_thread import LinearSensorThread
from core.threads.ltc_thread import LTCThread
from event_manager import EventManager

def init_hardware(pi):
    linear_sensor, LTC, motor = None, None, None
    
    try:
        logging.info("Initializing linear sensor...")
        linear_sensor = serial_reader.LinearSensorReader('/dev/ttyACM0', 115200)
        if not linear_sensor.connect():
            raise Exception("Failed to connect to linear sensor")
        
        logging.info("Initializing photo interruptor...")
        LTC = PhotoInterruptor(pi)
        
        logging.info("Initializing motor...")
        motor = tmc2209.TMC2209()
        motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
        
        return linear_sensor, LTC, motor
        
    except Exception as e:
        logging.error(f"Failed to initialize hardware components: {e}")
        if linear_sensor:
            try:
                linear_sensor.disconnect()
            except:
                pass
        return None, None, None
    
def init_pi():
    pi = pigpio.pi()
    if not pi.connected:
        logging.error("Failed to connect to pigpio daemon")
        return None
    return pi

def check_all_hardware(pi, LTC, motor):
    if not all([pi, LTC, motor]):
        logging.error("Hardware initialization failed. Exiting.")
        return None
    
def check_mm_value(linear_sensor, mm_value, since_last_mm, config):
    new_mm = linear_sensor.get_position()
    if new_mm is not None:
        return new_mm, 0.0
    else:
        return mm_value, since_last_mm + config.SAMPLE_TIME
    
def init_threads(linear_sensor, LTC, motor):
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
    
    return linear_sensor, LTC, motor, manager