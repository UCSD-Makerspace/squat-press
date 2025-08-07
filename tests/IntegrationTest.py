import lx3302a.SENTReader.SENTReader as SENTReader
import time
import pigpio
import sys
from os import path
from config import SystemConfig
import Dispenser.TMC2209.tmc2209 as tmc2209
import ADC.ADC as ADC

def low_pass_filter(prev_filtered: float, new_data: float, alpha: float) -> float:
    return (prev_filtered * alpha) + (new_data * (1 - alpha))

def run_loop(p, pi, adc, motor, config):
    start = time.time()
    filtered_data = 0.0
    below_threshold = False
    status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()

    while (time.time() - start) < config.RUN_TIME:
        time.sleep(config.SAMPLE_TIME)
        try:
            adc.update()
            adc_data = adc.get_data_percent()
            if adc_data == 0:
                print("Out of bounds!")
                continue
        except Exception as e:
            print(f"Error reading ADC data: {e}")
            continue

        if errors == 0 or errors == 8:
            most_recent_data = data1
            new_data = True
            time_since_last_data = 0
        else:
            time_since_last_data += config.SAMPLE_TIME
            if time_since_last_data > 5.0:
                print("No valid data received for 5 seconds, restarting SENTReader")
                p.stop()
                p = SENTReader.SENTReader(pi, config.ENT_GPIO)
                time.sleep(3.0)
                time_since_last_data = 0
                continue
    
        most_recent_data = data
        filtered_data = low_pass_filter(filtered_data, most_recent_data, config.ALPHA)

        print(f"Filtered Pos: {filtered_data:.5f}, Current Pos: {most_recent_data:.5f}")

        if filtered_data < config.THRESHOLD and not below_threshold:
            below_threshold = True
            dist = config.DISPENSE_ANGLE * config.DISPENSE_DIR
            thread, _ = motor.rotate_degrees_threaded(dist, 0)
            print("Dispensing Pellet...")
        elif filtered_data > config.THRESHOLD and below_threshold:
            below_threshold = False

def setup(config):
    pi = pigpio.pi()
    p = SENTReader.SENTReader(pi, config.SENT_GPIO)
    adc = ADC.ADC(pi)
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    return p, pi, adc, motor

def main():
    config = SystemConfig()
    p, pi, adc, motor = setup(config)

    try:
        run_loop(p, pi, adc, motor, config)
    finally:
        pi.stop()

if __name__ == "__main__":
    main()
