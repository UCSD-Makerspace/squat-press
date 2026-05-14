"""
GPIO SYNC — per-sample CSV logger with per-cycle lift summary + live dashboard
==============================================================================
GPIO pin (BCM 21) from ESP32 gates logging:
  HIGH → cycle start (t=0), begin buffering samples
  LOW  → cycle end, flush CSV, compute peak stats, push to dashboard

Per-sample CSV: data/csv/YYYY.MM.DD/gpio_sensorN_HHMMSS.csv
  columns: cycle, time_s, position_mm, raw_value

Peak is defined as any sample where position_mm >= PEAK_THRESHOLD_MM (19 mm).
"""

import serial
import time
import csv
import threading
from pathlib import Path
from datetime import datetime
import RPi.GPIO as GPIO

from lift_server import start_server, update_latest_lift

BAUD_RATE         = 115200
SYNC_GPIO_PIN     = 21
PEAK_THRESHOLD_MM = 19.0

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

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

# ── GPIO sync state ───────────────────────────────────────────────────────────

_lock             = threading.Lock()
_in_cycle         = False
_cycle_start_time = None
_cycle_count      = 0
_last_cycle_start = None   # absolute start time of the previous cycle

def sync_callback(channel):
    global _in_cycle, _cycle_start_time, _cycle_count, _last_cycle_start
    t = time.time()
    state = GPIO.input(SYNC_GPIO_PIN)
    with _lock:
        if state == GPIO.HIGH:
            _last_cycle_start = _cycle_start_time   # save before overwriting
            _in_cycle         = True
            _cycle_start_time = t
            _cycle_count     += 1
            print(f"\n>>> CYCLE {_cycle_count} STARTED  {datetime.fromtimestamp(t).strftime('%H:%M:%S')}")
        else:
            _in_cycle = False
            duration = (t - _cycle_start_time) * 1000 if _cycle_start_time else 0
            print(f">>> CYCLE {_cycle_count} ENDED  ({duration:.0f} ms total)")

# ── Port helper ───────────────────────────────────────────────────────────────

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

# ── Per-cycle summary ─────────────────────────────────────────────────────────

def _finish_cycle(cyc_num, cyc_start_abs, prev_start_abs, samples):
    """Called once per cycle after the GPIO falls LOW. samples is a list of
    {'time_s': float, 'mm': float} dicts collected during the cycle."""
    positions = [s['mm'] for s in samples]
    peak_mm   = max(positions)

    at_peak      = [s for s in samples if s['mm'] >= PEAK_THRESHOLD_MM]
    peak_samples = len(at_peak)
    peak_dur_ms  = (
        (at_peak[-1]['time_s'] - at_peak[0]['time_s']) * 1000
        if len(at_peak) >= 2 else 0.0
    )

    lift_time = datetime.fromtimestamp(cyc_start_abs).strftime('%H:%M:%S') if cyc_start_abs else '??:??:??'
    gap_s     = round(cyc_start_abs - prev_start_abs, 2) if prev_start_abs is not None else None

    print(f"\n{'─' * 54}")
    print(f"  Cycle {cyc_num:>3}  │  Lift @ {lift_time}  │  Gap: {f'{gap_s:.2f}s' if gap_s else 'N/A'}")
    print(f"  Peak height:   {peak_mm:.2f} mm")
    print(f"  At peak:       {peak_samples} samples ≥ {PEAK_THRESHOLD_MM:.0f} mm  ({peak_dur_ms:.1f} ms)")
    print(f"  Total samples: {len(samples)}")
    print(f"{'─' * 54}\n")

    update_latest_lift(
        cycle        = cyc_num,
        lift_time    = lift_time,
        gap_s        = gap_s,
        peak_mm      = round(peak_mm, 2),
        peak_samples = peak_samples,
        peak_dur_ms  = round(peak_dur_ms, 1),
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sensor_num = input("Sensor number: ").strip()
    raw_port   = input("Serial port (e.g. ACM0 or /dev/ttyACM0) [ACM0]: ").strip()
    max_cycles = int(input("Max cycles to record (0 for infinite): ").strip() or 0)

    port = _resolve_port(raw_port)
    ser  = serial.Serial(port, BAUD_RATE, timeout=0.02)
    print(f"Connected to {port}")

    for _ in range(10):
        ser.write(b'F'); ser.readline(); time.sleep(0.005)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SYNC_GPIO_PIN, GPIO.IN)
    GPIO.add_event_detect(SYNC_GPIO_PIN, GPIO.BOTH, callback=sync_callback, bouncetime=10)

    start_server()

    date_str = datetime.now().strftime("%Y.%m.%d")
    ts       = datetime.now().strftime("%H%M%S")
    out_dir  = _PROJECT_ROOT / "data" / "csv" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gpio_sensor{sensor_num}_{ts}.csv"

    f = open(out_path, "w", newline="")
    w = csv.writer(f)
    w.writerow(["cycle", "time_s", "position_mm", "raw_value"])

    print(f"Logging to {out_path}")
    print("Uncapped sampling (no averaging, no sleep). Ctrl+C to stop.\n")

    mm = None; raw = None
    count = 0; t_report = time.time()

    prev_in_cycle = False
    cycle_samples = []
    active_cyc    = None   # (cyc_num, cyc_start_abs, prev_start_abs)

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
                in_cycle   = _in_cycle
                cyc_start  = _cycle_start_time
                cyc        = _cycle_count
                last_start = _last_cycle_start

            if max_cycles > 0 and cyc > max_cycles:
                print(f"\nReached max cycles ({max_cycles}). Stopping.")
                break

            # Rising edge: new cycle started — reset buffer and snapshot metadata
            if in_cycle and not prev_in_cycle:
                cycle_samples = []
                active_cyc    = (cyc, cyc_start, last_start)

            # During cycle: log to CSV and buffer sample for end-of-cycle analysis
            if in_cycle and mm is not None and cyc_start is not None:
                t_rel = round(t0 - cyc_start, 4)
                w.writerow([cyc, t_rel, round(mm, 4), raw])
                f.flush()
                cycle_samples.append({'time_s': t_rel, 'mm': round(mm, 4)})

            # Falling edge: cycle just ended — compute peak stats and push to dashboard
            if prev_in_cycle and not in_cycle and cycle_samples and active_cyc:
                _finish_cycle(*active_cyc, cycle_samples)
                cycle_samples = []

            prev_in_cycle = in_cycle

            now = time.time()
            if now - t_report >= 5.0:
                hz = count / (now - t_report)
                print(f"[sampler] {hz:.0f} Hz")
                count = 0; t_report = now

    except KeyboardInterrupt:
        print(f"\nDone. Saved to {out_path}")
    finally:
        f.close(); GPIO.cleanup(); ser.close()

if __name__ == "__main__":
    main()
