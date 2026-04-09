"""
High-rate linear sensor reader with internal averaging
=======================================================
Reads sensor as fast as possible in a background thread (~300-500Hz achievable
on RPi at 115200 baud), applies a rolling average internally, and outputs
smoothed values at a fixed 100Hz rate to CSV.

This separates two concerns:
  - Raw read rate: as fast as serial allows (~300-500Hz)
  - Output rate: fixed 100Hz (10ms intervals)
  - Smoothing: rolling average over a configurable window

Key improvement over naive sleep-based approach:
  - Background thread reads continuously with no sleep — maximises sample rate
  - Output loop uses absolute time targets so 100Hz means 100Hz
  - Each logged value is the mean of all raw reads since the last log point
  - read_count per row tells you how many raw samples went into each average
"""

import serial
import time
import csv
import threading
import RPi.GPIO as GPIO
from datetime import datetime
from collections import deque
from pathlib import Path
import importlib.util

# ── Config ────────────────────────────────────────────────────────────────────
SERIAL_PORT     = "/dev/ttyACM1"
BAUD_RATE       = 115200
OUTPUT_RATE_HZ  = 100           # How often we log a value (100Hz = 10ms)
SMOOTH_WINDOW   = 5             # Rolling average over N raw samples
                                # At ~300Hz raw, window=5 = ~16ms smoothing
                                # At ~500Hz raw, window=5 = ~10ms smoothing
SYNC_GPIO_PIN   = 21

# Load shared calibration table from tests/linear_sensor/calibration/calibration_table.py
cal_path = Path(__file__).resolve().parents[1] / "calibration" / "calibration_table.py"
spec = importlib.util.spec_from_file_location("calibration_table", cal_path)
cal_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal_mod)
CALIBRATION_TABLE = cal_mod.calibration_table

def interpolate(raw_value):
    table = CALIBRATION_TABLE
    if raw_value >= table[0][1]:  return table[0][0]
    if raw_value <= table[-1][1]: return table[-1][0]
    for i in range(len(table) - 1):
        mm1, r1 = table[i]
        mm2, r2 = table[i+1]
        if r2 <= raw_value <= r1:
            ratio = (raw_value - r1) / (r2 - r1)
            return mm1 + ratio * (mm2 - mm1)
    return None


# ── Shared state ──────────────────────────────────────────────────────────────
# Thread-safe rolling buffer of recent (timestamp, mm) readings
_buffer_lock = threading.Lock()
_raw_buffer  = deque()          # (timestamp_s, mm_value) tuples

# GPIO sync state
_gpio_lock        = threading.Lock()
_in_cycle         = False
_cycle_start_time = None
_cycle_count      = 0


# ── GPIO callback ─────────────────────────────────────────────────────────────
def sync_callback(channel):
    global _in_cycle, _cycle_start_time, _cycle_count
    t = time.time()
    state = GPIO.input(SYNC_GPIO_PIN)
    with _gpio_lock:
        if state == GPIO.HIGH:
            _in_cycle         = True
            _cycle_start_time = t
            _cycle_count     += 1
            print(f"\n>>> CYCLE {_cycle_count} STARTED")
        else:
            _in_cycle = False
            duration = t - _cycle_start_time if _cycle_start_time else 0
            print(f">>> CYCLE {_cycle_count} ENDED  ({duration:.3f}s)")


# ── Background serial reader thread ───────────────────────────────────────────
def serial_reader_thread(ser, stop_event):
    """
    Reads sensor as fast as possible. No sleep — just read continuously.
    Pushes (timestamp, mm) into _raw_buffer.
    Benchmarks itself and prints achieved read rate every 5 seconds.
    """
    count = 0
    t_report = time.time()

    while not stop_event.is_set():
        t0 = time.time()
        try:
            ser.write(b'F')
            response = ser.readline().decode('ascii', errors='replace').strip()
            if response:
                raw = int(response.split()[0], 16)
                mm  = interpolate(raw)
                if mm is not None:
                    with _buffer_lock:
                        _raw_buffer.append((t0, mm))
                    count += 1
        except Exception:
            pass

        # Report achieved rate every 5s
        now = time.time()
        if now - t_report >= 5.0:
            rate = count / (now - t_report)
            print(f"[reader] {rate:.0f} Hz raw read rate  (buffer size: {len(_raw_buffer)})")
            count = 0
            t_report = now


# ── Main logging loop ─────────────────────────────────────────────────────────
def main():
    sensor_num = input("Enter sensor number (e.g. 1): ").strip()

    # Serial
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.02)
    print(f"Connected to {SERIAL_PORT}")

    # Warm up
    for _ in range(10):
        ser.write(b'F')
        ser.readline()
        time.sleep(0.005)

    # GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.BOTH, callback=sync_callback, bouncetime=10)

    # Start background reader
    stop_event = threading.Event()
    reader = threading.Thread(target=serial_reader_thread, args=(ser, stop_event), daemon=True)
    reader.start()

    # CSV
    ts_str   = datetime.now().strftime("%H%M%S")
    filename = f"sensor{sensor_num}_{ts_str}.csv"
    csv_file = open(filename, "w", newline="")
    writer   = csv.writer(csv_file)
    writer.writerow(["cycle", "time_s", "position_mm", "read_count", "raw_rate_hz"])

    print(f"Logging to {filename} at {OUTPUT_RATE_HZ}Hz output. Ctrl+C to stop.\n")

    output_interval = 1.0 / OUTPUT_RATE_HZ
    next_log        = time.time()
    rolling_window  = deque(maxlen=SMOOTH_WINDOW)

    try:
        while True:
            now = time.time()

            # Drain buffer: collect all raw reads since last log point
            with _buffer_lock:
                # Take all samples that arrived before now
                fresh = [v for t, v in _raw_buffer if t <= now]
                # Keep only samples after now in buffer
                while _raw_buffer and _raw_buffer[0][0] <= now:
                    _raw_buffer.popleft()

            if fresh:
                rolling_window.extend(fresh)

            # Compute smoothed value from rolling window
            if rolling_window:
                smoothed   = sum(rolling_window) / len(rolling_window)
                read_count = len(fresh)   # how many raw reads went into this output tick

                # Estimate raw rate from recent buffer activity
                raw_rate = read_count / output_interval if output_interval > 0 else 0

                with _gpio_lock:
                    in_cycle   = _in_cycle
                    cycle_start = _cycle_start_time
                    cycle_num  = _cycle_count

                if in_cycle and cycle_start is not None:
                    elapsed = round(now - cycle_start, 4)
                    writer.writerow([cycle_num, elapsed, round(smoothed, 4), read_count, round(raw_rate, 1)])
                    csv_file.flush()

            # Fixed-rate output: advance target time
            next_log += output_interval
            sleep_for = next_log - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_log = time.time()   # fell behind — reset

    except KeyboardInterrupt:
        print(f"\nStopped. Saved to {filename}")
    finally:
        stop_event.set()
        csv_file.close()
        GPIO.cleanup()
        ser.close()


if __name__ == "__main__":
    main()