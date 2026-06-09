"""
csv_writer.py — persist a LiftEvent to data/csv/<date>/ and save config snapshot.
"""

import csv
import threading
from datetime import datetime
from pathlib import Path

from .lift_detector import LiftEvent

# Root of repo (3 levels up from this file)
_REPO_ROOT = Path(__file__).resolve().parents[4]
CSV_ROOT   = _REPO_ROOT / "data" / "csv"

_write_lock = threading.Lock()
_sensor_num = 1   # set by main before any lifts fire


def set_sensor_number(n: int):
    global _sensor_num
    _sensor_num = n


def save_lift(event: LiftEvent):
    date_str  = datetime.now().strftime("%Y.%m.%d")
    ts_str    = datetime.now().strftime("%H%M%S")
    base_name = f"sensor{_sensor_num}_lift{event.lift_number}_{ts_str}"

    out_dir = CSV_ROOT / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{base_name}.csv"
    cfg_path = out_dir / f"{base_name}_config.txt"

    with _write_lock:
        # ── CSV ──────────────────────────────────────────────────────────────
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time_s", "position_mm", "raw_value"])
            w.writerows(event.samples)

        # ── Config snapshot ──────────────────────────────────────────────────
        with open(cfg_path, "w") as f:
            f.write(f"# Config snapshot for {base_name}\n")
            f.write(f"# lift_number      : {event.lift_number}\n")
            f.write(f"# peak_mm          : {event.peak_mm:.3f}\n")
            f.write(f"# within_cooldown  : {event.within_cooldown}\n")
            f.write(f"# samples          : {len(event.samples)}\n")
            f.write("#\n")
            for k, v in event.config_snap.items():
                f.write(f"{k} = {v}\n")

    cooldown_tag = " [WITHIN COOLDOWN]" if event.within_cooldown else ""
    print(
        f"[csv] lift {event.lift_number}{cooldown_tag} → "
        f"{csv_path.relative_to(_REPO_ROOT)}  "
        f"({len(event.samples)} samples, peak {event.peak_mm:.2f} mm)"
    )
