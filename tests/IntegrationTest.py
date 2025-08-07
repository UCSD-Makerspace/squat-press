import lx3302a.SENTReader.SENTReader as SENTReader
import time
import pigpio
import threading
from os import path
from config import SystemConfig
from time import sleep
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import Dispenser.TMC2209.tmc2209 as tmc2209
from Dispenser.PhotoInterruptor.PhotoInterruptor import PhotoInterruptor
import ADC.ADC as ADC

TEST_LINEAR_SENSOR = False
TEST_PHOTO_INTERRUPTOR = True
TEST_MOTOR = True

def test_linear_sensor(pi, config):
    logging.info("Testing Linear Sensor...")
    p = SENTReader.SENTReader(pi, config.SENT_GPIO)
    start = time.time()
    while time.time() - start < config.RUN_TIME:
        status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()
        print(f"Status: {status}, Data1: {data1}, Data2: {data2}, Ticktime: {ticktime}, CRC: {crc}, Errors: {errors}, SyncPulse: {syncPulse}")
        time.sleep(0.1)
    p.stop()

def test_photo_interruptor(pi, config):
    logging.info("Testing Photo Interruptor...")
    LTC = PhotoInterruptor(pi)
    last_state = LTC.get_detected()
    start = time.time()

    while (time.time() - start) < config.RUN_TIME:
        time.sleep(0.1)
        LTC.update()
        cur_state = LTC.get_detected()

        if last_state is False and cur_state is True:
            print(f"Pellet dispensed: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
        if last_state is True and cur_state is False:
            print(f"Pellet taken: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
        last_state = cur_state

def test_motor():
    logging.info("Testing Stepper Motor...")
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    dir = 1
    while True:
        dir = -dir
        dist = dir*180
        thread, _ = motor.rotate_degrees_threaded(dist, 0)
        print(f"Rotating {dist} degrees...")
        thread.join()
        print("Rotation complete.")
        print(f"Current position: {motor.position:.2f} revolutions")
        sleep(1)

def main():
    config = SystemConfig()
    pi = pigpio.pi()

    threads = []

    try:
        if TEST_LINEAR_SENSOR:
            test_linear_sensor(pi, config)
            thread = threading.Thread(target=test_linear_sensor, args=(pi, config))
            threads.append(thread)
            thread.start()
        if TEST_PHOTO_INTERRUPTOR:
            test_photo_interruptor(pi, config)
            thread = threading.Thread(target=test_photo_interruptor, args=(pi, config))
            threads.append(thread)
            thread.start()
        if TEST_MOTOR:
            test_motor()
            thread = threading.Thread(target=test_motor, args=())
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logging.info("Tests interrupted by user.")
    finally:
        pi.stop()
        logging.info("Tests completed. Cleaning up...")

if __name__ == "__main__":
    main()