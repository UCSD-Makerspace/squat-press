import time
import pigpio
import threading
from os import path
from tests.config import SystemConfig
from time import sleep
import logging
from PhaseManager import PhaseManager
from phases import Warmup, Lift, Cooldown, ProgressiveOverload

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import ADC.ADC as ADC
import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import lx3302a.SENTReader.SENTReader as SENTReader
from rotate import dispense

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

def dispenser_worker(motor, LTC, phase_manager):
    logging.info("Dispenser worker thread started")

    while True:
        current_phase = phase_manager.get_current_phase()
        if not current_phase:
            logging.warning("Current phase not found in dispenser_thread")
            time.sleep(0.1)
            continue

        if current_phase.pellet_queue > 0:
            logging.info(f"Dispensing pellet (queue: {current_phase.pellet_queue}) in {current_phase.config.name}")

            if dispense(motor, LTC):
                current_phase.pellet_dispensed()
                logging.info(f"Pellet dispensed in {current_phase.config.name}")
            else:
                current_phase.pellet_queue -= 1
                logging.warning(f"Pellet dispense failed, subtracting from queue")

        else:
            time.sleep(0.1)
        
        if phase_manager.is_trial_complete():
            logging.info("Dispenser woker thread ending (Trial complete)")
            break

def main():
    config = SystemConfig()
    pi = None
    p = None
    motor = None
    
    # Temporary: will eventually have GUI To auto-set these settings
    phase_list = [
        Warmup(req_lifts=3, lift_increment=1, max_pellets=5, duration=120),
        Lift(req_lifts = 5, lift_increment = 2, duration=120, max_pellets=20),
        Cooldown(pellet_interval=3.0, duration=60)
    ]

    phase_manager = PhaseManager(phase_list)

    try:
        pi = pigpio.pi()
        if not pi.connected:
            logging.error("Failed to connect to pigpio daemon")
            return
        
        p, LTC, motor = init_hardware(pi, config)
        if not all([p, LTC, motor]):
            logging.error("Hardware initialization failed. Exiting.")
            return
        
        if not phase_manager.start_trial():
            logging.error("Failed to start trial: no phases available")
            return

        dispenser_thread = threading.Thread(
            target = dispenser_worker,
            args=(motor, LTC, phase_manager),
            daemon=True
        )
        dispenser_thread.start()

        # Init sensor variables
        last_LTC_state = LTC.get_detected()
        filtered_SENT = 0.0
        time_since_last_SENT = 0.0
        recent_SENT = 0

        start = time.time()
        while phase_manager.is_trial_active and (time.time() - start < config.RUN_TIME):
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
                        logging.warning("No valid data received for 5 seconds, restarting SENTReader")
                        p.stop()
                        p = SENTReader.SENTReader(pi, SENT_GPIO)
                        time.sleep(3.0)
                        time_since_last_SENT = 0.0
                        continue

                if new_SENT_data:
                    filtered_SENT = (filtered_SENT * config.ALPHA) + (recent_SENT * (1-config.ALPHA))
                    
                current_phase = phase_manager.get_current_phase()
                if current_phase:
                    if current_phase.should_dispense(filtered_SENT):
                        logging.info(f"Lift threshold met in {current_phase.config.name}")
                        current_phase.add_to_queue()

                    if phase_manager.check_phase_completion():
                        logging.info("Phase transition occurred")
    
                if last_LTC_state is False and cur_LTC_state is True:
                    print(f"Pellet detected: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
                
                elif last_LTC_state is True and cur_LTC_state is False:
                    print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")

                last_LTC_state = cur_LTC_state

                if int(current_time) % 30 == 0:
                    stats = phase_manager.get_trial_stats()
                    if stats['current_phase_stats']:
                        phase_stats = stats['current_phase_stats']
                        logging.info(f"Trial progress: Phase {stats['current_phase_name']}, "
                                     f"Pellets: {phase_stats['pellets_dispensed']}, "
                                     f"Queue: {phase_stats['pellet_queue']}")
                 
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                break
    
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logging.error(f"Unexpected error in main: {e}")
    finally:
        if phase_manager.is_trial_active:
            phase_manager.end_trial()

        if 'dispenser_thread' in locals() and dispenser_thread.is_alive():
            logging.info("Waiting for dispenser thread to finish...")
            dispenser_thread.join(timeout=5.0)

        cleanup_hardware(p, motor, pi)
        final_stats = phase_manager.get_trial_stats()
        logging.info(f"Trial completed. Total phases: {final_stats['total_phases']}, "
                    f"Phases completed: {final_stats['phases_completed']}, "
                    f"Duration: {final_stats['trial_duration']:.2f}s")


if __name__ == "__main__":
    main()