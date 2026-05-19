"""
Dual-mode lift detector — GPIO sync + software rolling-average fallback
=======================================================================
Detection priority:
  1. GPIO pin (BCM 21) from ESP32 — HIGH = cycle start, LOW = cycle end
  2. Software threshold — rolling average of last SW_WINDOW samples crosses
     SW_LIFT_THRESHOLD_MM to start a cycle, drops back below to end it

Whichever fires first starts the cycle. GPIO takes priority when both active.

Per-sample CSV: data/csv/YYYY.MM.DD/gpio_sensorN_HHMMSS.csv
  columns: cycle, time_s, position_mm, raw_value

Peak is defined as any sample where position_mm >= PEAK_THRESHOLD_MM (19 mm).
"""

import serial
import time
import csv
import io
import base64
import statistics
import threading
from collections import deque
from pathlib import Path
from datetime import datetime
from lift_server import start_server, update_latest_lift
import RPi.GPIO as GPIO

try:
    import matplotlib
    matplotlib.use('Agg')   # non-interactive — must come before pyplot import
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False
    print("[warn] matplotlib not found — graphs will be disabled. Install with: sudo apt install python3-matplotlib")

BAUD_RATE            = 115200
SYNC_GPIO_PIN        = 21
PEAK_THRESHOLD_MM    = 19.0
SW_LIFT_THRESHOLD_MM = 0.175   # rolling avg above this → software cycle start
SW_WINDOW            = 10    # number of samples in the rolling average

# file lives at data/validation_scripts/html_server_display/
# parents[3] is the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

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
_last_cycle_start = None

def sync_callback(channel):
    global _in_cycle, _cycle_start_time, _cycle_count, _last_cycle_start
    t = time.time()
    state = GPIO.input(SYNC_GPIO_PIN)
    with _lock:
        if state == GPIO.HIGH:
            _last_cycle_start = _cycle_start_time
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

# ── Plot helpers ──────────────────────────────────────────────────────────────

def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return b64

def _make_lift_plot(cyc_num, times, positions) -> str | None:
    if not _HAS_MPL:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor('#0d0d0d')
    ax.set_facecolor('#141414')
    ax.plot(times, positions, color='#4a9eff', linewidth=1.5)
    ax.fill_between(times, positions, alpha=0.12, color='#4a9eff')
    ax.axhline(PEAK_THRESHOLD_MM, color='#ff6b6b', linestyle='--',
               linewidth=1.0, label=f'{PEAK_THRESHOLD_MM:.0f} mm detection threshold')
    ax.set_xlabel('Time within cycle (s)', color='#aaa')
    ax.set_ylabel('Position (mm)', color='#aaa')
    ax.set_title(f'Cycle {cyc_num} — Lift Trace', color='#ddd')
    ax.tick_params(colors='#888')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333')
    ax.grid(True, alpha=0.15, color='#555')
    ax.legend(fontsize=8, facecolor='#1a1a1a', labelcolor='#ccc', edgecolor='#333')
    fig.tight_layout()
    return _fig_to_b64(fig)

def _make_hz_plot(cyc_num, hz_list, hz_mean, hz_std) -> str | None:
    if not _HAS_MPL or len(hz_list) < 2:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor('#0d0d0d')
    ax.set_facecolor('#141414')
    bins = min(40, max(5, len(hz_list) // 3))
    ax.hist(hz_list, bins=bins, color='#a78bfa', edgecolor='#0d0d0d', linewidth=0.4)
    ax.axvline(hz_mean, color='#ff6b6b', linestyle='--', linewidth=1.5,
               label=f'Mean {hz_mean:.1f} Hz')
    ax.axvspan(hz_mean - hz_std, hz_mean + hz_std, alpha=0.15, color='#ff6b6b',
               label=f'±1σ  ({hz_std:.1f} Hz)')
    ax.set_xlabel('Instantaneous sampling frequency (Hz)', color='#aaa')
    ax.set_ylabel('Count', color='#aaa')
    ax.set_title(f'Cycle {cyc_num} — Sampling Frequency Distribution', color='#ddd')
    ax.tick_params(colors='#888')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333')
    ax.grid(True, alpha=0.15, color='#555')
    ax.legend(fontsize=8, facecolor='#1a1a1a', labelcolor='#ccc', edgecolor='#333')
    fig.tight_layout()
    return _fig_to_b64(fig)

# ── Per-cycle summary ─────────────────────────────────────────────────────────

def _finish_cycle(cyc_num, cyc_start_abs, prev_start_abs, samples):
    positions = [s['mm']     for s in samples]
    times     = [s['time_s'] for s in samples]

    peak_mm          = max(positions)
    at_peak          = [s for s in samples if s['mm'] >= PEAK_THRESHOLD_MM]
    peak_samples     = len(at_peak)
    peak_dur_ms      = (
        (at_peak[-1]['time_s'] - at_peak[0]['time_s']) * 1000
        if len(at_peak) >= 2 else 0.0
    )
    lift_duration_s  = times[-1] - times[0] if len(times) >= 2 else 0.0

    lift_time = datetime.fromtimestamp(cyc_start_abs).strftime('%H:%M:%S') if cyc_start_abs else '??:??:??'
    gap_s     = round(cyc_start_abs - prev_start_abs, 2) if prev_start_abs is not None else None

    # Inter-sample Hz stats
    dts     = [times[i+1] - times[i] for i in range(len(times) - 1) if times[i+1] > times[i]]
    hz_list = [1.0 / dt for dt in dts]
    hz_mean = statistics.mean(hz_list)          if len(hz_list) >= 1 else 0.0
    hz_std  = statistics.stdev(hz_list)         if len(hz_list) >= 2 else 0.0
    dt_std  = statistics.stdev(dts)             if len(dts)     >= 2 else 0.0

    # Worst-case position error from timing jitter (1σ)
    # error = max_velocity (mm/s) × timing_std (s)
    vels          = [abs(positions[i+1] - positions[i]) / dts[i] for i in range(len(dts))]
    max_vel_mm_s  = max(vels) if vels else 0.0
    mm_error_1sig = round(max_vel_mm_s * dt_std, 4)

    print(f"\n{'─' * 54}")
    print(f"  Cycle {cyc_num:>3}  │  Lift @ {lift_time}  │  Gap: {f'{gap_s:.2f}s' if gap_s else 'N/A'}")
    print(f"  Peak height:     {peak_mm:.2f} mm")
    print(f"  Above threshold: {peak_samples} samples ≥ {PEAK_THRESHOLD_MM:.0f} mm  ({peak_dur_ms:.1f} ms)")
    print(f"  Lift duration:   {lift_duration_s * 1000:.1f} ms  ({len(samples)} samples)")
    print(f"  Sampling:        {hz_mean:.1f} Hz ± {hz_std:.1f} Hz  →  ±{mm_error_1sig:.4f} mm error (1σ)")
    print(f"{'─' * 54}\n")

    graph_b64    = _make_lift_plot(cyc_num, times, positions)
    hz_graph_b64 = _make_hz_plot(cyc_num, hz_list, hz_mean, hz_std)

    update_latest_lift(
        cycle          = cyc_num,
        lift_time      = lift_time,
        gap_s          = gap_s,
        peak_mm        = round(peak_mm, 2),
        peak_samples   = peak_samples,
        peak_dur_ms    = round(peak_dur_ms, 1),
        lift_duration_s= round(lift_duration_s, 3),
        hz_mean        = round(hz_mean, 1),
        hz_std         = round(hz_std, 1),
        mm_error_1sig  = mm_error_1sig,
        max_vel_mm_s   = round(max_vel_mm_s, 1),
        graph_b64      = graph_b64,
        hz_graph_b64   = hz_graph_b64,
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
    active_cyc    = None

    # Software detection state
    sw_window     = deque(maxlen=SW_WINDOW)
    sw_in_cycle   = False
    sw_cyc_start  = None
    sw_last_start = None
    sw_cyc_count  = 0

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

            # ── GPIO state ────────────────────────────────────────────────────
            with _lock:
                gpio_in_cycle   = _in_cycle
                gpio_cyc_start  = _cycle_start_time
                gpio_cyc        = _cycle_count
                gpio_last_start = _last_cycle_start

            # ── Software rolling-average detection ────────────────────────────
            if mm is not None:
                sw_window.append(mm)

            if len(sw_window) == SW_WINDOW:
                sw_avg = sum(sw_window) / SW_WINDOW

                if not sw_in_cycle and sw_avg > SW_LIFT_THRESHOLD_MM:
                    sw_last_start = sw_cyc_start
                    sw_cyc_start  = t0
                    sw_cyc_count += 1
                    sw_in_cycle   = True
                    print(f"\n>>> [SW] CYCLE {sw_cyc_count} STARTED  {datetime.fromtimestamp(t0).strftime('%H:%M:%S')}")

                elif sw_in_cycle and sw_avg <= SW_LIFT_THRESHOLD_MM:
                    sw_in_cycle = False
                    print(f">>> [SW] CYCLE {sw_cyc_count} ENDED")

            # ── Combine: GPIO takes priority, SW is fallback ───────────────────
            if gpio_in_cycle:
                in_cycle   = True
                cyc_start  = gpio_cyc_start
                cyc        = gpio_cyc
                last_start = gpio_last_start
            elif sw_in_cycle:
                in_cycle   = True
                cyc_start  = sw_cyc_start
                cyc        = sw_cyc_count
                last_start = sw_last_start
            else:
                in_cycle   = False
                cyc_start  = None
                cyc        = max(gpio_cyc, sw_cyc_count)
                last_start = None

            if max_cycles > 0 and cyc > max_cycles:
                print(f"\nReached max cycles ({max_cycles}). Stopping.")
                break

            # Rising edge: reset buffer and snapshot metadata
            if in_cycle and not prev_in_cycle:
                cycle_samples = []
                active_cyc    = (cyc, cyc_start, last_start)

            # During cycle: log to CSV and buffer for end-of-cycle analysis
            if in_cycle and mm is not None and cyc_start is not None:
                t_rel = round(t0 - cyc_start, 4)
                w.writerow([cyc, t_rel, round(mm, 4), raw])
                f.flush()
                cycle_samples.append({'time_s': t_rel, 'mm': round(mm, 4)})

            # Falling edge: compute stats and push to dashboard
            if prev_in_cycle and not in_cycle and cycle_samples and active_cyc:
                _finish_cycle(*active_cyc, cycle_samples)
                cycle_samples = []

            prev_in_cycle = in_cycle

            now = time.time()
            if now - t_report >= 5.0:
                sw_avg_disp = f"{sum(sw_window)/len(sw_window):.2f}" if sw_window else "—"
                hz = count / (now - t_report)
                print(f"[sampler] {hz:.0f} Hz  |  sw_avg {sw_avg_disp} mm")
                count = 0; t_report = now

    except KeyboardInterrupt:
        print(f"\nDone. Saved to {out_path}")
    finally:
        f.close(); GPIO.cleanup(); ser.close()

if __name__ == "__main__":
    main()
