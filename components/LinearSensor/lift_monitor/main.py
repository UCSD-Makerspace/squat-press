"""
continuous_lift_monitor — main entry point
==========================================
Usage:
    python -m components.LinearSensor.lift_monitor.main
    python -m components.LinearSensor.lift_monitor.main --gui
    python -m components.LinearSensor.lift_monitor.main --gui --sensor 2
    python -m components.LinearSensor.lift_monitor.main COM3 --gui

Flags:
    --gui          Launch live scrolling graph window
    --sensor N     Sensor number used in CSV filenames (default 1)
    <port>         Serial port hint (otherwise auto-detected / from config)

Mid-session hot-reload:
    Press Enter in the terminal to get a menu:
        R  — reload config from disk
        S  — print current stats
        Q  — quit
"""

import argparse
import sys
import threading
import time
from pathlib import Path

# Allow running as a script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from .config      import Config
from .sensor_io   import SensorBus, reader_thread
from .lift_detector import LiftDetector
from .csv_writer  import save_lift, set_sensor_number

CALIBRATION_SAMPLES = 15


# ── Calibration / startup poll ────────────────────────────────────────────────

def calibration_loop(bus: SensorBus, cfg: Config) -> bool:
    """
    Poll CALIBRATION_SAMPLES live values, let user decide to continue,
    reload config, or stop.  Returns True to continue, False to exit.
    """
    while True:
        print("\n" + "─" * 60)
        print(f"Polling {CALIBRATION_SAMPLES} live values for offset calibration…")
        print(f"  Current zero_offset_calibration = {cfg.zero_offset:.4f} mm")
        print("─" * 60)

        samples_seen = 0
        timeout_start = time.perf_counter()
        while samples_seen < CALIBRATION_SAMPLES:
            if time.perf_counter() - timeout_start > 30:
                print("[calibration] timeout — no sensor data in 30 s")
                break
            ts, ps, _ = bus.snapshot()
            new_count = len(ps)
            if new_count > samples_seen:
                for mm in ps[samples_seen:new_count]:
                    print(f"  {mm:+.4f} mm  (offset applied: {cfg.zero_offset:.4f})")
                    samples_seen += 1
                    if samples_seen >= CALIBRATION_SAMPLES:
                        break
            time.sleep(0.05)

        print("\n")
        print("  Y — continue to monitoring")
        print("  R — restart (reload config.cfg first, then re-poll)")
        print("  S — stop / exit")
        choice = input("Choice [Y/R/S]: ").strip().upper()

        if choice == "Y":
            return True
        elif choice == "R":
            cfg.reload()
            print(f"[config] reloaded — zero_offset now {cfg.zero_offset:.4f} mm")
        elif choice == "S":
            return False
        else:
            print("  (unrecognised — enter Y, R, or S)")


# ── Terminal control loop (hot-reload / stats) ────────────────────────────────

def _terminal_loop(cfg: Config, detector, stop_event: threading.Event):
    print("\n[monitor] Running. Press Enter for menu (R=reload config, S=stats, Q=quit).")
    while not stop_event.is_set():
        try:
            line = input()
        except EOFError:
            break
        choice = line.strip().upper()
        if choice == "R":
            cfg.reload()
            print(f"[config] reloaded. lift_threshold={cfg.lift_threshold}, "
                  f"zero_offset={cfg.zero_offset}")
        elif choice == "S":
            print(f"[stats] lifts confirmed so far: {detector._lift_count}")
        elif choice == "Q":
            print("[monitor] Stopping…")
            stop_event.set()
        else:
            print("  R — reload config   S — stats   Q — quit")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Continuous lift monitor for linear sensor")
    parser.add_argument("port",       nargs="?", default=None,
                        help="Serial port (optional; overrides config)")
    parser.add_argument("--gui",      action="store_true",
                        help="Show live scrolling graph")
    parser.add_argument("--sensor",   type=int, default=1,
                        help="Sensor number used in CSV filenames (default 1)")
    args = parser.parse_args()

    cfg = Config()
    if args.port:
        cfg._data["port"] = args.port  # CLI port overrides config

    set_sensor_number(args.sensor)

    bus        = SensorBus()
    stop_event = threading.Event()

    # Start sensor reader thread
    t_reader = threading.Thread(
        target=reader_thread,
        args=(bus, cfg, stop_event),
        daemon=True,
    )
    t_reader.start()

    # Wait briefly for the reader to connect before calibration poll
    print("[monitor] Waiting for sensor…")
    deadline = time.perf_counter() + 10.0
    while not bus.is_connected and time.perf_counter() < deadline:
        time.sleep(0.1)
    if not bus.is_connected:
        print("[monitor] No sensor found in 10 s — continuing anyway (will reconnect).")

    # Calibration loop
    should_continue = calibration_loop(bus, cfg)
    if not should_continue:
        stop_event.set()
        print("[monitor] Exited.")
        return

    # Build detector
    detector = LiftDetector(cfg, on_lift_confirmed=save_lift)

    # Feed detector from sensor bus in a background thread
    def _detection_loop():
        last_ts = None  # last timestamp processed; avoids maxlen wrap issues
        while not stop_event.is_set():
            ts, ps, raws = bus.snapshot()
            if not ts:
                time.sleep(0.01)
                continue
            # detect bus reset (reconnect resets t0) — restart processing
            if last_ts is not None and ts[-1] < last_ts:
                last_ts = None
            start = 0
            if last_ts is not None:
                found = False
                for i, t in enumerate(ts):
                    if t > last_ts:
                        start = i
                        found = True
                        break
                if not found:
                    time.sleep(0.005)
                    continue
            for i in range(start, len(ts)):
                detector.process(ts[i], ps[i], raws[i])
            last_ts = ts[-1]
            time.sleep(0.005)

    threading.Thread(target=_detection_loop, daemon=True).start()

    # Terminal control (non-blocking input in a thread)
    threading.Thread(
        target=_terminal_loop,
        args=(cfg, detector, stop_event),
        daemon=True,
    ).start()

    print(f"[monitor] Monitoring sensor {args.sensor}. "
          f"Lifts will be saved to data/csv/<date>/")

    if args.gui:
        from .gui import run_gui
        run_gui(bus, detector, cfg, stop_event)
    else:
        # Headless: just block until stop_event
        try:
            while not stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    stop_event.set()
    print("[monitor] Done.")


if __name__ == "__main__":
    main()
