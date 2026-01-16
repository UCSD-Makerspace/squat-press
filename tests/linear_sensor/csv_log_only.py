import Dispenser.LinearSensor.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv
from typing import Optional

sample_rates = [0.01, 0.025, 0.050, 0.1]

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
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm", "raw_value"])

    start_time = time.time()

    mm_value = None
    raw_val = None
    prev_mm_value = 0

    try:
        while True:
            mm_value, raw_val = check_mm_value(sensor, mm_value, raw_val)

            if mm_value is not None:
                prev_mm_value = mm_value
                elapsed = time.time() - start_time

                elapsed = round(elapsed, 3)
                mm_value = round(mm_value, 3)

                csv_writer.writerow([elapsed, mm_value, raw_val])
                csv_file.flush()    
                time.sleep(sample_rates[0])      

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        csv_file.close()
        print(f"Data saved to sensor_log_{timestamp}.csv")

if __name__ == "__main__":
    main()