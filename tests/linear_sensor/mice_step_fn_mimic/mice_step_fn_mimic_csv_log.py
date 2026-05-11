"""
Mouse lift CSV logger for mice_step_fn_mimic.
=============================================

This logger is the GPIO-free companion to the minimum peak validation script.
It continuously samples the LX3302A sensor over serial, detects each lift cycle
from the sensor signal itself, and writes rows in the standard repository CSV
shape:

  cycle,time_s,position_mm,raw_value

Cycle boundaries are inferred with a small hysteresis state machine:
  - a new cycle starts when the measured position rises above START_MM
  - the cycle ends after the signal falls back below END_MM for several samples

This is intentionally simpler than the jitter test logger because we only need
peak validation, not the full motion shape or an external GPIO sync pulse.
"""

import csv
import serial
import time
from collections import deque
from datetime import datetime

BAUD_RATE = 115200
SERIAL_TIMEOUT_S = 0.02

# The lift starts from rest near 0 mm and peaks at about 19.5 mm.
# These thresholds are conservative enough to avoid rest noise while still
# capturing the full cycle in a GPIO-free setup.
START_MM = 1.0
END_MM = 0.7
START_CONFIRM_SAMPLES = 2
END_CONFIRM_SAMPLES = 5
MIN_CYCLE_DURATION_S = 0.060
MAX_IDLE_BUFFER_SAMPLES = 8

CALIBRATION_TABLE = [
    (0.000, 10615), (1.000, 10444), (2.000, 10284), (3.000, 10136),
    (4.000,  9992), (5.000,  9826), (6.000,  9644), (7.000,  9556),
    (8.000,  9463), (9.000,  9184), (10.000,  8982), (11.000,  8732),
    (12.000, 8457), (13.000,  8289), (14.000,  8125), (15.000,  7959),
    (16.000, 7789), (17.000,  7637), (18.000,  7447), (19.000,  7267),
    (20.000, 7042), (21.000,  6865), (22.000,  6684), (23.000,  6471),
    (24.000, 6254), (25.000,  6114),
]


def interpolate(raw):
    table = CALIBRATION_TABLE
    if raw >= table[0][1]:
        return table[0][0]
    if raw <= table[-1][1]:
        return table[-1][0]
    for i in range(len(table) - 1):
        mm1, r1 = table[i]
        mm2, r2 = table[i + 1]
        if r2 <= raw <= r1:
            return mm1 + (raw - r1) / (r2 - r1) * (mm2 - mm1)
    return None


def _resolve_port(port_text, default="ACM0"):
    if not port_text:
        port_text = default
    if port_text.startswith("/dev/") or port_text.startswith("COM"):
        return port_text
    port_lower = port_text.lower()
    if port_lower.startswith("acm"):
        return f"/dev/tty{port_lower.upper()}"
    if port_lower.isdigit():
        return f"/dev/ttyACM{port_lower}"
    return port_text


def main():
    sensor_num = input("Sensor number: ").strip()
    raw_port = input("Serial port (e.g. ACM0 or /dev/ttyACM0) [ACM0]: ").strip()
    max_cycles = int(input("Max cycles to record (0 for infinite): ").strip() or 0)

    port = _resolve_port(raw_port)
    ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT_S)
    print(f"Connected to {port}")

    for _ in range(10):
        ser.write(b"F")
        ser.readline()
        time.sleep(0.005)

    ts = datetime.now().strftime("%H%M%S")
    filename = f"mice_step_fn_sensor{sensor_num}_{ts}.csv"
    csv_file = open(filename, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(["cycle", "time_s", "position_mm", "raw_value"])

    print("GPIO-free cycle detection running (no sync input, no sleep). Ctrl+C to stop.\n")

    sample_count = 0
    report_start = time.time()
    current_cycle = 0
    in_cycle = False
    start_time = None
    start_candidate_count = 0
    end_candidate_count = 0
    peak_mm = None
    peak_raw = None
    peak_time_s = None
    baseline_buffer = deque(maxlen=MAX_IDLE_BUFFER_SAMPLES)

    try:
        while True:
            t0 = time.time()
            ser.write(b"F")
            response = ser.readline().decode("ascii", errors="replace").strip()

            raw = None
            mm = None
            if response:
                try:
                    raw = int(response.split()[0], 16)
                    mm = interpolate(raw)
                    sample_count += 1
                except Exception:
                    pass

            if mm is None or raw is None:
                now = time.time()
                if now - report_start >= 5.0:
                    hz = sample_count / (now - report_start)
                    print(f"[sampler] {hz:.0f} Hz")
                    sample_count = 0
                    report_start = now
                continue

            if not in_cycle:
                baseline_buffer.append((t0, mm, raw))
                if mm >= START_MM:
                    start_candidate_count += 1
                else:
                    start_candidate_count = 0

                if start_candidate_count >= START_CONFIRM_SAMPLES:
                    current_cycle += 1
                    in_cycle = True
                    start_time = t0
                    end_candidate_count = 0
                    peak_mm = mm
                    peak_raw = raw
                    peak_time_s = 0.0
                    print(f"\n>>> CYCLE {current_cycle} STARTED")

                    # Include a small pre-roll so the logged cycle has a cleaner start.
                    for buffered_t, buffered_mm, buffered_raw in baseline_buffer:
                        writer.writerow([current_cycle, round(buffered_t - start_time, 4), round(buffered_mm, 4), buffered_raw])
                    csv_file.flush()
                    baseline_buffer.clear()
                else:
                    # Keep only a few idle samples for a small pre-roll.
                    if len(baseline_buffer) > MAX_IDLE_BUFFER_SAMPLES:
                        baseline_buffer.popleft()
            else:
                elapsed = t0 - start_time if start_time is not None else 0.0
                writer.writerow([current_cycle, round(elapsed, 4), round(mm, 4), raw])
                csv_file.flush()

                if peak_mm is None or mm > peak_mm:
                    peak_mm = mm
                    peak_raw = raw
                    peak_time_s = elapsed

                if mm <= END_MM:
                    end_candidate_count += 1
                else:
                    end_candidate_count = 0

                if elapsed >= MIN_CYCLE_DURATION_S and end_candidate_count >= END_CONFIRM_SAMPLES:
                    in_cycle = False
                    duration = elapsed
                    valid = peak_mm is not None and peak_mm >= 19.0
                    print(
                        f">>> CYCLE {current_cycle} ENDED  "
                        f"(duration={duration:.3f}s, peak={peak_mm:.3f}mm at {peak_time_s:.3f}s, valid={valid})"
                    )
                    start_time = None
                    start_candidate_count = 0
                    end_candidate_count = 0
                    peak_mm = None
                    peak_raw = None
                    peak_time_s = None
                    baseline_buffer.clear()

                    if max_cycles > 0 and current_cycle >= max_cycles:
                        print(f"\nReached max cycles ({max_cycles}). Stopping.")
                        break

            now = time.time()
            if now - report_start >= 5.0:
                hz = sample_count / (now - report_start)
                print(f"[sampler] {hz:.0f} Hz")
                sample_count = 0
                report_start = now

    except KeyboardInterrupt:
        print(f"\nDone. Saving to {filename}")
    finally:
        csv_file.close()
        ser.close()


if __name__ == "__main__":
    main()
