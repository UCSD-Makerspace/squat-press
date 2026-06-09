"""
config.py — load and hot-reload lift_monitor.cfg
"""

import configparser
import threading
from pathlib import Path

CFG_PATH = Path(__file__).resolve().parents[1] / "lift_monitor.cfg"


class Config:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}
        self.load()

    def load(self):
        p = configparser.ConfigParser()
        p.read(CFG_PATH)
        with self._lock:
            self._data = {
                "port":                   p.get("sensor",      "port",                   fallback="").strip(),
                "baud_rate":              p.getint("sensor",   "baud_rate",              fallback=115200),
                "lift_threshold":         p.getfloat("detection", "lift_threshold",      fallback=19.0),
                "min_lift_duration":      p.getfloat("detection", "min_lift_duration",   fallback=0.040),
                "drop_threshold":         p.getfloat("detection", "drop_threshold",      fallback=5.0),
                "pellet_cooldown":        p.getfloat("detection", "pellet_cooldown",     fallback=3.0),
                "window_size":            p.getint("recording",   "window_size",         fallback=200),
                "zero_offset":            p.getfloat("calibration", "zero_offset_calibration", fallback=0.0),
                "gui_window_size":        p.getfloat("gui",     "gui_window_size",       fallback=10.0),
            }
        print(f"[config] loaded from {CFG_PATH}")

    def reload(self):
        self.load()

    def __getattr__(self, name):
        try:
            with self._lock:
                return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
