"""
GPIO SYNC ONLY — no rolling average, single-threaded original read rate
=======================================================================
GPIO pin sets t=0 as before. No background thread, no averaging.
Reads one sample per output tick, same as the original script.

Output CSV columns: cycle, time_s, position_mm, raw_value
"""

import serial
import time
import csv
import threading
import RPi.GPIO as GPIO
from datetime import datetime

SERIAL_PORT     = "/dev/ttyACM0"
BAUD_RATE       = 115200
SAMPLE_INTERVAL = 0.010
SYNC_GPIO_PIN   = 21

CALIBRATION_TABLE = [
    (0.000, 10615), (1.000, 10444), (2.000, 10284), (3.000, 10136),
    (4.000,  9992), (5.000,  9826), (6.000,  9644), (7.000,  9556),
    (8.000,  9463), (9.000,  9184),(10.000,  8982),(11.000,  8732),
    (12.000, 8457),(13.000,  8289),(14.000,  8125),(15.000,  7959),
    (16.000, 7789),(17.000,  7637),(18.000,  7447),(19.000,  7267),
    (20.000, 7042),(21.000,  6865),(22.000,  6684),(23.000,  6471),
    (24.000, 6254),(25.000,  6114),
]

def interpolate(raw):
    t = CALIBRATION_TABLE
    if raw >= t[0][1]:  return t[0][0]
    if raw <= t[-1][1]: return t[-1][0]
    for i in range(len(t) - 1):
        mm1, r1 = t[i]; mm2, r2 = t[i+1]
        if r2 <= raw <= r1:
            return mm1 + (raw - r1) / (r2 - r1) * (mm2 - mm1)
    return None

_lock             = threading.Lock()
_in_cycle         = False
_cycle_start_time = None
_cycle_count      = 0

def sync_callback(channel):
    global _in_cycle, _cycle_start_time, _cycle_count
    t = time.time()
    state = GPIO.input(SYNC_GPIO_PIN)
    with _lock:
        if state == GPIO.HIGH:
            _in_cycle = True; _cycle_start_time = t; _cycle_count += 1
            print(f"\n>>> CYCLE {_cycle_count} STARTED")
        else:
            _in_cycle = False
            print(f">>> CYCLE {_cycle_count} ENDED ({time.time()-_cycle_start_time:.3f}s)")

def main():
    sensor_num = input("Sensor number: ").strip()
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    for _ in range(5): ser.write(b'F'); ser.readline(); time.sleep(0.005)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.BOTH, callback=sync_callback, bouncetime=10)

    ts = datetime.now().strftime("%H%M%S")
    f  = open(f"gpio_sensor{sensor_num}_{ts}.csv", "w", newline="")
    w  = csv.writer(f)
    w.writerow(["cycle", "time_s", "position_mm", "raw_value"])

    print("GPIO-sync-only capture running (no averaging). Ctrl+C to stop.\n")
    next_tick = time.time()
    mm = None; raw = None

    try:
        while True:
            t0 = time.time()
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            if resp:
                try:
                    raw = int(resp.split()[0], 16)
                    mm  = interpolate(raw)
                except: pass

            with _lock:
                in_cycle = _in_cycle; start = _cycle_start_time; cyc = _cycle_count

            if in_cycle and mm is not None and start is not None:
                w.writerow([cyc, round(t0 - start, 4), round(mm, 4), raw])
                f.flush()

            next_tick += SAMPLE_INTERVAL
            sleep_for  = next_tick - time.time()
            if sleep_for > 0: time.sleep(sleep_for)
            else: next_tick = time.time()

    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        f.close(); GPIO.cleanup(); ser.close()

if __name__ == "__main__":
    main()