"""
Jitter test CSV logger
======================
Detects GPIO sync pulses (RISING edge only) from jitter_test.ino.
Direction is inferred from the alternating UP/DOWN pattern in the Arduino sketch
(stroke % 2 == 0 -> UP) rather than pulse-width measurement, because the 200-600us
pulses are shorter than RPi GPIO interrupt latency — GPIO.input() in the callback
would already read LOW for both edges, making width measurement unreliable.

Logs sensor position from each rising edge until the next rising edge (~105ms window:
5ms motor + 100ms coast). Uncapped sampling, no sleep.

Output CSV columns: stroke_no, direction, time_ms, position_mm, raw_value
"""

import serial
import time
import csv
import threading
import RPi.GPIO as GPIO
from datetime import datetime

BAUD_RATE     = 115200
SYNC_GPIO_PIN = 21

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
_in_stroke        = False
_stroke_start     = None
_stroke_direction = None
_stroke_count     = 0

# Arduino alternates UP/DOWN starting with UP (stroke % 2 == 0 -> going_up)
_DIRECTIONS = ["UP", "DOWN"]

def sync_callback(channel):
    global _in_stroke, _stroke_start, _stroke_direction, _stroke_count
    t = time.time()
    with _lock:
        _stroke_count    += 1
        _in_stroke        = True
        _stroke_start     = t
        _stroke_direction = _DIRECTIONS[(_stroke_count - 1) % 2]
        print(f"\n>>> STROKE {_stroke_count} {_stroke_direction}")

def _resolve_port(s, default="ACM0"):
    if not s:
        s = default
    if s.startswith("/dev/") or s.startswith("COM"):
        return s
    s_low = s.lower()
    if s_low.startswith("acm"):
        return f"/dev/tty{s_low.upper()}"
    if s_low.isdigit():
        return f"/dev/ttyACM{s_low}"
    return s

def main():
    sensor_num  = input("Sensor number: ").strip()
    raw_port    = input("Serial port (e.g. ACM0 or /dev/ttyACM0) [ACM0]: ").strip()
    max_strokes = int(input("Max strokes to record (0 for infinite): ").strip() or 0)

    port = _resolve_port(raw_port)
    ser  = serial.Serial(port, BAUD_RATE, timeout=None)
    print(f"Connected to {port}")

    for _ in range(10):
        ser.write(b'F'); ser.readline(); time.sleep(0.005)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.RISING, callback=sync_callback, bouncetime=5)

    ts = datetime.now().strftime("%H%M%S")
    f  = open(f"jitter_sensor{sensor_num}_{ts}.csv", "w", newline="")
    w  = csv.writer(f)
    w.writerow(["stroke_no", "direction", "time_ms", "position_mm", "raw_value"])

    print("Uncapped sampling running (no sleep). Ctrl+C to stop.\n")

    mm = None; raw = None
    count = 0; t_report = time.time()

    try:
        while True:
            t0 = time.time()
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            try:
                raw = int(resp.split()[0], 16)
                mm  = interpolate(raw)
                count += 1
            except: pass

            with _lock:
                in_stroke = _in_stroke
                start     = _stroke_start
                direction = _stroke_direction
                stroke_no = _stroke_count

            if max_strokes > 0 and stroke_no > max_strokes:
                print(f"\nReached max strokes ({max_strokes}). Stopping.")
                break

            if in_stroke and mm is not None and start is not None:
                w.writerow([stroke_no, direction, round((t0 - start) * 1000, 2), round(mm, 4), raw])
                f.flush()

            now = time.time()
            if now - t_report >= 5.0:
                hz = count / (now - t_report)
                print(f"[sampler] {hz:.0f} Hz")
                count = 0; t_report = now

    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        f.close(); GPIO.cleanup(); ser.close()

if __name__ == "__main__":
    main()
