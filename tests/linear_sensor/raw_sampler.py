import serial
import time
import threading
import csv
from datetime import datetime
from collections import deque
from pathlib import Path
import importlib.util

import RPi.GPIO as GPIO

# ── Config ────────────────────────────────────────────────────────────────────
SENSOR_PORT     = "/dev/ttyACM0"
SENSOR_BAUD     = 115200
SYNC_GPIO_PIN   = 17               # BCM pin wired to ESP32 RPI_SYNC_PIN
OUTPUT_CSV      = Path("jitter_results.csv")

# Pulse width thresholds (microseconds) matching ESP32 syncStrokeStart()
UP_PULSE_MAX_US   = 400   # < 400us = UP stroke
DOWN_PULSE_MIN_US = 400   # >= 400us = DOWN stroke

# ── Calibration ───────────────────────────────────────────────────────────────
cal_path = Path(__file__).resolve().parents[1] / "calibration" / "calibration_table.py"
spec     = importlib.util.spec_from_file_location("calibration_table", cal_path)
cal_mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal_mod)
CALIBRATION_TABLE = cal_mod.calibration_table

# ── Shared state ──────────────────────────────────────────────────────────────
raw_buffer   = deque()          # (timestamp_s, mm)
buffer_lock  = threading.Lock()
sync_events  = []               # list of dicts written by GPIO ISR
events_lock  = threading.Lock()
stop_event   = threading.Event()


# ── Calibration interpolation ─────────────────────────────────────────────────
def interpolate(raw_value):
    table = CALIBRATION_TABLE
    if raw_value >= table[0][1]:
        return table[0][0]
    if raw_value <= table[-1][1]:
        return table[-1][0]
    for i in range(len(table) - 1):
        mm1, r1 = table[i]
        mm2, r2 = table[i + 1]
        if r2 <= raw_value <= r1:
            ratio = (raw_value - r1) / (r2 - r1)
            return mm1 + ratio * (mm2 - mm1)
    return None


# ── GPIO sync ISR ─────────────────────────────────────────────────────────────
_pulse_start = None

def _gpio_callback(channel):
    """
    Called on both edges of the sync pin.
    Rising edge  → record pulse start time.
    Falling edge → measure pulse width, classify direction, log event.
    """
    global _pulse_start
    now = time.time()

    if GPIO.input(channel) == GPIO.HIGH:
        _pulse_start = now
    else:
        if _pulse_start is None:
            return
        pulse_us = (now - _pulse_start) * 1e6
        direction = "UP" if pulse_us < UP_PULSE_MAX_US else "DOWN"
        with events_lock:
            sync_events.append({
                "timestamp": _pulse_start,   # when motion started
                "direction": direction,
                "pulse_us":  pulse_us,
            })
        _pulse_start = None


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(
        SYNC_GPIO_PIN,
        GPIO.BOTH,
        callback=_gpio_callback,
        bouncetime=1        # 1ms debounce — strokes are much longer
    )
    print(f"GPIO {SYNC_GPIO_PIN} armed for sync pulses")


# ── Sensor reader thread ──────────────────────────────────────────────────────
def sensor_reader_loop(ser):
    """
    Reads the sensor at maximum serial rate, pushes (timestamp, mm) into
    raw_buffer. Prints actual read rate every 5 seconds.
    """
    count    = 0
    t_report = time.time()

    while not stop_event.is_set():
        t0 = time.time()
        try:
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            if resp:
                raw = int(resp.split()[0], 16)
                mm  = interpolate(raw)
                if mm is not None:
                    with buffer_lock:
                        raw_buffer.append((t0, mm))
                    count += 1
        except Exception:
            pass

        now = time.time()
        if now - t_report >= 5.0:
            print(f"[sensor] {count / (now - t_report):.0f} Hz")
            count    = 0
            t_report = now


# ── Analysis: match sync events to sensor readings ────────────────────────────
def analyze_stroke(event, all_samples, stroke_duration_s=0.005, expected_mm=0.35):
    """
    For a given sync event, find all sensor samples within the stroke window
    and compute: start mm, end mm, delta mm, sample count, vs expected.

    stroke_duration_s : how long the ESP32 ran the motor (5ms default)
    expected_mm       : ground truth from your calibration (0.35mm at vel=2000)
    """
    t_start = event["timestamp"]
    t_end   = t_start + stroke_duration_s + 0.010  # +10ms margin for sensor lag

    window = [(t, mm) for t, mm in all_samples if t_start <= t <= t_end]

    if len(window) < 2:
        return None

    mm_start  = window[0][1]
    mm_end    = window[-1][1]
    delta_mm  = mm_end - mm_start
    n_samples = len(window)
    error_mm  = abs(abs(delta_mm) - expected_mm)

    return {
        "timestamp":   datetime.fromtimestamp(t_start).strftime("%H:%M:%S.%f")[:-3],
        "direction":   event["direction"],
        "pulse_us":    f"{event['pulse_us']:.0f}",
        "mm_start":    f"{mm_start:.4f}",
        "mm_end":      f"{mm_end:.4f}",
        "delta_mm":    f"{delta_mm:.4f}",
        "expected_mm": f"{expected_mm:.4f}",
        "error_mm":    f"{error_mm:.4f}",
        "n_samples":   n_samples,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Connect to sensor
    ser = serial.Serial(SENSOR_PORT, SENSOR_BAUD, timeout=0.02)
    print(f"Sensor connected: {SENSOR_PORT} @ {SENSOR_BAUD}")

    # Warm up sensor
    for _ in range(10):
        ser.write(b'F')
        ser.readline()
        time.sleep(0.005)

    # Start background reader
    reader = threading.Thread(target=sensor_reader_loop, args=(ser,), daemon=True)
    reader.start()

    # Arm GPIO
    setup_gpio()

    # CSV header
    csv_fields = [
        "timestamp", "direction", "pulse_us",
        "mm_start", "mm_end", "delta_mm",
        "expected_mm", "error_mm", "n_samples"
    ]
    csv_file = OUTPUT_CSV.open("w", newline="")
    writer   = csv.DictWriter(csv_file, fieldnames=csv_fields)
    writer.writeheader()

    print("\nRunning — Ctrl+C to stop\n")
    print(f"{'Time':<15} {'Dir':<6} {'Delta':>8} {'Expected':>10} {'Error':>8} {'Samples':>8}")
    print("-" * 60)

    processed_events = 0

    try:
        while True:
            time.sleep(0.1)  # check for new events 10x/sec

            with events_lock:
                new_events = sync_events[processed_events:]

            with buffer_lock:
                all_samples = list(raw_buffer)

            for event in new_events:
                # Only analyze events old enough that the stroke window has passed
                if time.time() - event["timestamp"] < 0.050:
                    continue  # stroke may still be in progress

                result = analyze_stroke(event, all_samples)
                processed_events += 1

                if result is None:
                    print(f"  [!] {event['direction']} stroke at "
                          f"{datetime.fromtimestamp(event['timestamp']).strftime('%H:%M:%S.%f')[:-3]}"
                          f" — no sensor data in window")
                    continue

                writer.writerow(result)
                csv_file.flush()

                print(
                    f"{result['timestamp']:<15} "
                    f"{result['direction']:<6} "
                    f"{result['delta_mm']:>8} mm "
                    f"{result['expected_mm']:>10} mm "
                    f"{result['error_mm']:>8} mm "
                    f"{result['n_samples']:>6} samples"
                )

    except KeyboardInterrupt:
        print("\n\nStopping...")
        stop_event.set()
    finally:
        GPIO.cleanup()
        ser.close()
        csv_file.close()

        # Session summary
        with events_lock:
            total = len(sync_events)
        print(f"\nTotal sync events captured : {total}")
        print(f"Results saved to           : {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()