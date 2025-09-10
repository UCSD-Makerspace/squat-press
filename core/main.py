from os import path
from tests.config import SystemConfig
from time import sleep
from PhaseManager import PhaseManager
from phases import Warmup, Lift, Cooldown
import logging
import time
import threading
import queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

### Hardware imports ###
import ADC.ADC as ADC
import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
from rotate import dispense

### Helper method imports ###
from main_helpers import init_hardware, cleanup_hardware, init_pi, dispenser_worker, check_all_hardware, check_mm_value

def main():
    config = SystemConfig()
    pi = None
    p = None
    motor = None
    dispenser_thread = None
    
    # Temporary: will eventually have GUI To auto-set these settings
    phase_list = [
        Warmup(req_lifts=3, lift_increment=1, max_pellets=5, duration=120),
        Lift(req_lifts = 5, lift_increment = 2, max_pellets=20, duration=120),
        Cooldown(pellet_interval=3.0, duration=60)
    ]

    phase_manager = PhaseManager(phase_list)

    try:
        pi = init_pi()
        p, LTC, motor = init_hardware(pi)
        check_all_hardware(pi, LTC, motor)
        phase_manager.start_trial()

        if not phase_manager.start_trial():
            logging.error("Failed to start trial: no phases available")
            return

        # Create event queue for communication between threads
        pellet_event_queue = queue.Queue()
        dispenser_thread = threading.Thread(
            target = dispenser_worker,
            args=(motor, LTC, phase_manager, pellet_event_queue),
            daemon=True
        )
        dispenser_thread.start()

        pending_confirmations = []

        # Init sensor variables
        last_LTC_state, start, mm_value, since_last_mm, last_log_time = (
            LTC.get_detected(), time.time(), None, 0.0, 0.0
        )
        while phase_manager.is_trial_active and (time.time() - start < config.RUN_TIME):
            current_time = time.time()

            mm_value, since_last_mm = check_mm_value(p, mm_value, since_last_mm, config)


            time.sleep(config.SAMPLE_TIME)

            try:
                while True:
                    try:
                        event = pellet_event_queue.get_nowait()
                    except queue.Empty:
                        break
                    else:
                        if event['type'] == 'attempt_result':
                            if event['success']:
                                pending_confirmations.append({
                                    'attempt_id': event['attempt_id'],
                                    'timestamp': event['timestamp']
                                })
                                logging.info(f"Pellet attempt {event['attempt_id']} succeeded, waiting for LTC confirmation")
                        pellet_event_queue.task_done()
            except queue.Empty:
                pass

            timeout_confirmations = [
                p for p in pending_confirmations 
                if current_time - p['timestamp'] >= 10.0
            ]
            for timeout in timeout_confirmations:
                logging.warning(f"Pellet confirmation timeout for attempt {timeout['attempt_id']}")
                current_phase = phase_manager.get_current_phase()
                if current_phase:
                    current_phase.pellet_attempt_failed()
            
            pending_confirmations = [
                p for p in pending_confirmations 
                if current_time - p['timestamp'] < 10.0
            ]

            try:                
                LTC.update()
                cur_LTC_state = LTC.get_detected()

                if mm_value is not None and since_last_mm > 5.0:
                    logging.warning("No valid data received for 5 seconds, restarting SENTReader")
                    p.disconnect()
                    p = serial_reader.LinearSensorReader('/dev/ttyACM0', 115200)
                    if not p.connect():
                        logging.error("Failed to connect LinearSensorReader after restart")
                        continue
                    time.sleep(3.0)
                    since_last_mm = 0.0

                current_phase = phase_manager.get_current_phase()
                if current_phase:
                    if current_phase.should_dispense(mm_value):
                        logging.info(f"Lift threshold met in {current_phase.config.name}")
                        current_phase.add_to_queue()

                    if phase_manager.check_phase_completion():
                        logging.info("Phase transition occurred")

                if last_LTC_state is False and cur_LTC_state is True:
                    print(f"Pellet detected: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
                    
                    current_phase = phase_manager.get_current_phase()
                    if current_phase:
                        current_phase.pellet_confirmed_dispensed()
                        logging.info(f"Pellet confirmed dispensed in {current_phase.config.name}")
                    
                    if pending_confirmations:
                        confirmed = pending_confirmations.pop(0)
                        logging.info(f"Confirmed pellet from attempt {confirmed['attempt_id']}")

                elif last_LTC_state is True and cur_LTC_state is False:
                    print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")

                last_LTC_state = cur_LTC_state

                if current_time - last_log_time >= 30.0:
                    phase_manager.log_trial_progress(len(pending_confirmations))
                    last_log_time = current_time
                 
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

        if dispenser_thread and dispenser_thread.is_alive():
            logging.info("Waiting for dispenser thread to finish...")
            dispenser_thread.join(timeout=5.0)

        cleanup_hardware(p, motor, pi)
        final_stats = phase_manager.get_trial_stats()
        logging.info(f"Trial completed. Total phases: {final_stats['total_phases']}, "
                    f"Phases completed: {final_stats['phases_completed']}, "
                    f"Duration: {final_stats['trial_duration']:.2f}s")

if __name__ == "__main__":
    main()