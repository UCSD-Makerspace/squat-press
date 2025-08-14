import time
import pigpio
import threading
from os import path
from tests.config import SystemConfig
from time import sleep
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import ADC.ADC as ADC
import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import lx3302a.SENTReader.SENTReader as SENTReader
from rotate import rotate_step, dispense, jitter

#### Consts ####
SENT_GPIO = 18
MIN_SENT = 2100
MAX_SENT = 2800

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
        if motor:
            motor.stop()
        if pi:
            pi.stop()
        logging.info("Hardware cleanup completed")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

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
        
        last_LTC_state = LTC.get_detected()

        filtered_SENT = 0.0
        time_since_last_SENT = 0.0
        recent_SENT = 0

        start = time.time()
        while time.time() - start < config.RUN_TIME:
            current_time = time.time()
            time.sleep(config.SAMPLE_TIME)

            status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()
            new_SENT_data = False

            try:                
                LTC.update()
                cur_LTC_state = LTC.get_detected()

                if errors == 0 or errors == 8:
                    recent_SENT = data1
                    new_SENT_data = True
                    time_since_last_SENT = 0.0 
                else:
                    time_since_last_SENT += config.SAMPLE_TIME
                    if time_since_last_SENT > 5.0:
                        print("No valid data received for 5 seconds, restarting SENTReader")
                        p.stop()
                        p = SENTReader.SENTReader(pi, SENT_GPIO)
                        time.sleep(3.0)
                        time_since_last_SENT = 0.0
                        continue

                if new_SENT_data:
                    filtered_SENT = (filtered_SENT * config.ALPHA) + (recent_SENT * (1-config.ALPHA))
                    
                if MIN_SENT <= filtered_SENT <= MAX_SENT:
                    dispense(motor, LTC)

                #print(f"Filtered Data, {filtered_SENT:0.5f}, Current Data, {(recent_SENT if new_SENT_data else 'Old Data')}")
    
                if last_LTC_state is False and cur_LTC_state is True:
                    print(f"Pellet detected: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
                
                elif last_LTC_state is True and cur_LTC_state is False:
                    print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")

                last_LTC_state = cur_LTC_state
                
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