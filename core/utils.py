"""
This module contains utility functions for the main loop
"""

import logging
import pigpio
import queue
from collections import deque

from Dispenser.ESP32Motor import ESP32Motor
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
from lx3302a.SENTReader.serial_reader import LinearSensorReader

from core.threads.dispenser_thread import DispenserThread
from core.threads.linear_sensor_thread import LinearSensorThread
from core.threads.ltc_thread import LTCThread
from event_manager import EventManager

def init_hardware(pi):
    """Initialize hardware components: linear sensor, photo interruptor, and motor."""
    linear_sensor, ltc, motor = None, None, None
    try:
        logging.info("Initializing linear sensor...")
        linear_sensor = LinearSensorReader('/dev/ttyS0', 115200)

        if not linear_sensor.connect():
            raise Exception("Failed to connect to linear sensor")

        logging.info("Initializing photo interruptor...")
        ltc = PhotoInterruptor(pi)

        logging.info("Initializing motor...")
        motor = ESP32Motor(port = "/dev/serial0", baudrate=115200)
        if not motor.connect():
            raise Exception("Failed to connect to motor")

        return linear_sensor, ltc, motor

    except Exception as e:
        logging.error(f"Failed to initialize hardware components: {e}")
        if linear_sensor:
            try:
                linear_sensor.disconnect()
            except:
                pass
        return None, None, None

def init_pi():
    """Initialize pigpio and return the pi instance."""
    pi = pigpio.pi()
    if not pi.connected:
        logging.error("Failed to connect to pigpio daemon")
        return None
    return pi

def check_all_hardware(pi, ltc, motor):
    """Check if all hardware components are initialized properly."""
    if not all([pi, ltc, motor]):
        logging.error("Hardware initialization failed. Exiting.")
        return None

def init_threads(linear_sensor, ltc, motor):
    """Initialize and start threads for linear sensor, LTC, and dispenser."""
    event_queue = queue.Queue()
    plot_queue = queue.Queue()

    linear_thread = LinearSensorThread(linear_sensor, event_queue, plot_queue, 
                                       mm_threshold=10, recent_lifts=deque())
    ltc_thread = LTCThread(ltc, event_queue)
    dispenser_thread = DispenserThread(motor, event_queue)

    linear_thread.start()
    ltc_thread.start()
    dispenser_thread.start()

    # Main controller
    manager = EventManager(event_queue, dispenser_thread)
    manager.run()

    return linear_sensor, ltc, motor, manager
