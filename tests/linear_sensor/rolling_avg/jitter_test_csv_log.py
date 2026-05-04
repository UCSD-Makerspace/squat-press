"""
Jitter test CSV logger — pulse-width direction detection
=========================================================
Reads GPIO sync pin pulse width on the falling edge to determine stroke direction:
  < 400us HIGH → UP stroke
  >= 400us HIGH → DOWN stroke
Motor starts ~100us after falling edge. Logs sensor position from falling edge
until the next rising edge (covers full stroke + coast period).

Output CSV columns: stroke_no, direction, time_s, position_mm, raw_value
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
_rise_time        = None

def sync_callback(channel):
    global _in_stroke, _stroke_start, _stroke_direction, _stroke_count, _rise_time
    t = time.time()
    state = GPIO.input(SYNC_GPIO_PIN)
    with _lock:
        if state == GPIO.HIGH:
            # Rising edge: end of previous stroke, record rise time for width measurement
            _rise_time = t
            _in_stroke = False
        else:
            # Falling edge: measure width, determine direction, start logging
            if _rise_time is not None:
                width_s   = t - _rise_time
                direction = "UP" if width_s < 0.0004 else "DOWN"
                _in_stroke        = True
                _stroke_start     = t
                _stroke_direction = direction
                _stroke_count    += 1
                print(f"\n>>> STROKE {_stroke_count} {direction}  (pulse {width_s*1e6:.0f} us)")

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
    ser  = serial.Serial(port, BAUD_RATE, timeout=0.02)
    print(f"Connected to {port}")

    for _ in range(10):
        ser.write(b'F'); ser.readline(); time.sleep(0.005)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    # No bouncetime — pulses are 200-600us; any debounce window would swallow them
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.BOTH, callback=sync_callback)

    ts = datetime.now().strftime("%H%M%S")
    f  = open(f"jitter_sensor{sensor_num}_{ts}.csv", "w", newline="")
    w  = csv.writer(f)
    w.writerow(["stroke_no", "direction", "time_s", "position_mm", "raw_value"])

    print("Uncapped sampling running (no sleep). Ctrl+C to stop.\n")

    mm = None; raw = None
    count = 0; t_report = time.time()

    try:
        while True:
            t0 = time.time()
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            if resp:
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
                w.writerow([stroke_no, direction, round(t0 - start, 4), round(mm, 4), raw])
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
