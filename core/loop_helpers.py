from os import path
import logging
import pigpio
import time
import threading

import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import lx3302a.SENTReader.serial_reader as serial_reader
from rotate import dispense

def init_hardware(pi):
    p, LTC, motor = None, None, None
    
    try:
        logging.info("Initializing linear sensor...")
        p = serial_reader.LinearSensorReader('/dev/ttyACM0', 115200)
        if not p.connect():
            raise Exception("Failed to connect to linear sensor")
        
        logging.info("Initializing photo interruptor...")
        LTC = PhotoInterruptor(pi)
        
        logging.info("Initializing motor...")
        motor = tmc2209.TMC2209()
        motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
        
        return p, LTC, motor
        
    except Exception as e:
        logging.error(f"Failed to initialize hardware components: {e}")
        if p:
            try:
                p.disconnect()
            except:
                pass
        return None, None, None

def cleanup_hardware(p, motor, pi):
    try:
        if p:
            p.disconnect()
        if motor:
            motor.stop()
        if pi:
            pi.stop()
        logging.info("Hardware cleanup completed")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

def dispenser_worker(motor, LTC, phase_manager, pellet_event_queue):
    """Modified dispenser worker that communicates attempts"""
    
    logging.info("Dispenser worker thread started")

    while True:
        current_phase = phase_manager.get_current_phase()
        if not current_phase:
            time.sleep(0.1)
            continue

        if current_phase.pellet_queue > 0:
            logging.info(f"Starting pellet attempt (queue: {current_phase.pellet_queue})")
            
            current_phase.pellet_attempt_started()
            
            attempt_id = time.time()
            success = dispense(motor, LTC)
            
            pellet_event_queue.put({
                'type': 'attempt_result',
                'attempt_id': attempt_id,
                'success': success,
                'timestamp': time.time()
            })
            
            if not success:
                current_phase.pellet_attempt_failed()
                logging.warning("Pellet attempt failed")
        else:
            time.sleep(0.1)
        
        if phase_manager.is_trial_complete():
            logging.info("Dispenser worker thread ending")
            break

def start_dispenser_thread(motor, LTC, phase_manager, pellet_event_queue):
    dispenser_thread = threading.Thread(
        target=dispenser_worker,
        args=(motor, LTC, phase_manager, pellet_event_queue),
        daemon=True
    )
    dispenser_thread.start()
    return dispenser_thread

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

def check_mm_value(p, mm_value, since_last_mm, config):
    new_mm = p.get_position()
    if new_mm is not None:
        return new_mm, 0.0
    else:
        return mm_value, since_last_mm + config.SAMPLE_TIME