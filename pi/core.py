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
    if motor is None:
        logging.error("Motor not initialized, cannot dispense pellet")
        return
    
    logging.info("Dispensing pellet.")
    dir = 1
    dist = dir * 180
    try:
        thread, _ = motor.rotate_degrees_threaded(dist, 0)
        thread.join()
        logging.info("Pellet dispensed successfully")
    except Exception as e:
        logging.error(f"Failed to dispense pellet: {e}")

def init_hardware(pi, config):
    p, LTC, motor = None, None, None
    
    try:
        logging.info("Initializing SENT reader...")
        p = SENTReader.SENTReader(pi, config.SENT_GPIO)
        
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
                p.stop()
            except:
                pass
        return None, None, None

def cleanup_hardware(p, motor, pi):
    try:
        if p:
            p.stop()
        if pi:
            pi.stop()
        logging.info("Hardware cleanup completed")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

# Core loop for hardware communication #
def main():
    config = SystemConfig()
    pi = None
    p = None
    motor = None
    
    try:
        pi = pigpio.pi()
        if not pi.connected:
            logging.error("Failed to connect to pigpio daemon")
            return
        
        p, LTC, motor = init_hardware(pi, config)
        if not all([p, LTC, motor]):
            logging.error("Hardware initialization failed. Exiting.")
            return
        
        last_state = LTC.get_detected()
        start = time.time()

        while time.time() - start < config.RUN_TIME:
            time.sleep(0.1)
            
            try:
                LTC.update()
                cur_state = LTC.get_detected()
                
                if last_state is False and cur_state is True:
                    print(f"Pellet detected: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
                    dispense_pellet(motor)
                
                elif last_state is True and cur_state is False:
                    print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")

                last_state = cur_state
                
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                break
    
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logging.error(f"Unexpected error in main: {e}")
    finally:
        cleanup_hardware(p, motor, pi)

if __name__ == "__main__":
    main()