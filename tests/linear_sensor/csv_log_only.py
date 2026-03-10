import Dispenser.LinearSensor.serial_reader as serial_reader
import matplotlib.pyplot as plt
import csv
from datetime import datetime
import RPi.GPIO as GPIO
import threading
import time
from typing import Optional

sample_rates = [0.01, 0.025, 0.050, 0.1]

SYNC_GPIO_PIN = 21
in_cycle, cycle_start_time, cycle_count = False, None, 0
lock = threading.Lock()

def sync_callback(channel):
    """ Increment cycle count and mark cycle start time when sync pin changes state."""
    global in_cycle, cycle_start_time, cycle_count
    
    time.sleep(0.001)
    pin_state = GPIO.input(SYNC_GPIO_PIN)

    with lock:
        if pin_state == GPIO.HIGH:
            in_cycle = True
            cycle_start_time = time.time()
            cycle_count += 1
            print(f"\n>>> CYCLE {cycle_count} STARTED")
        else:
            in_cycle = False
            duration = time.time() - cycle_start_time if cycle_start_time else 0
            print(f">>> CYCLE {cycle_count} ENDED, duration: {duration:.3f} s")

def check_mm_value(sensor: serial_reader.LinearSensorReader, last_val: Optional[float], last_raw_val: Optional[float]):
    """Return (interpolated mm, raw decimal value)"""
    raw_val = sensor.send_command('F')
    if raw_val:
        try:
            decimal_value = int(raw_val.split()[0], 16)
            mm = sensor.interpolate(decimal_value)
            return mm, decimal_value
        except Exception as e:
            print(f"Parse error: {e}, raw={raw_val}")
    return last_val, last_raw_val

def main():
    global cycle_start_time, cycle_count, in_cycle
    # Get user input for which number linear sensor we are using
    sensor_num = input("Enter sensor number (e.g. 1): ").strip()
    if not sensor_num.isdigit():
        print("Invalid input. Please enter a number.")
        return

    # --- Connect to sensor ---
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    # --- Setup GPIO pins for cycle sync ---
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.BOTH, callback=sync_callback, bouncetime=50)

    print("Testing GPIO 21 state:")
    for i in range(20):
        state = GPIO.input(SYNC_GPIO_PIN)
        print(f"GPIO 21: {state}")
        time.sleep(0.1)

    # --- Setup CSV logging ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor{sensor_num}_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm", "raw_value"])

    mm_value = None
    raw_val = None

    try:
        while True:
            mm_value, raw_val = check_mm_value(sensor, mm_value, raw_val)

            with lock:
                currently_in_cycle = in_cycle
                current_start_time = cycle_start_time
                current_cycle = cycle_count

            if currently_in_cycle and mm_value is not None and current_start_time is not None:
                elapsed = time.time() - current_start_time
                elapsed = round(elapsed, 3)
                mm_value = round(mm_value, 3)

                csv_writer.writerow([elapsed, mm_value, raw_val])
                csv_file.flush() 

            time.sleep(sample_rates[0])      

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        csv_file.close()
        print(f"Data saved to sensor{sensor_num}_{timestamp}.csv")

if __name__ == "__main__":
    main()