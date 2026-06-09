"""
sensor_io.py — background serial polling thread.

Writes into a shared SensorBus that other modules read from.
Decoupled from any GUI or detection logic.
"""

import threading
import time
from collections import deque

import serial
import serial.tools.list_ports

from components.LinearSensor import interpolate


MAX_PTS    = 8000
HZ_SMOOTH  = 30


class SensorBus:
    """Thread-safe shared state between the reader thread and consumers."""
    def __init__(self, max_pts=MAX_PTS):
        self._lock      = threading.Lock()
        self.times      = deque(maxlen=max_pts)
        self.positions  = deque(maxlen=max_pts)
        self.raw_vals   = deque(maxlen=max_pts)
        self.connected  = False
        self.t0         = 0.0

    def push(self, t_abs: float, mm: float, raw: int):
        with self._lock:
            self.times.append(t_abs - self.t0)
            self.positions.append(mm)
            self.raw_vals.append(raw)

    def snapshot(self):
        with self._lock:
            return list(self.times), list(self.positions), list(self.raw_vals)

    def clear(self, t0: float):
        with self._lock:
            self.times.clear()
            self.positions.clear()
            self.raw_vals.clear()
            self.t0 = t0
            self.connected = True

    def set_connected(self, v: bool):
        with self._lock:
            self.connected = v

    @property
    def is_connected(self):
        with self._lock:
            return self.connected


def _find_port(hint: str) -> list[str]:
    candidates = [p.device for p in serial.tools.list_ports.comports()]
    if hint and hint in candidates:
        return [hint] + [c for c in candidates if c != hint]
    return candidates


def reader_thread(bus: SensorBus, cfg_ref, stop_event: threading.Event):
    """
    Runs forever in a daemon thread. Reconnects automatically on disconnect.
    cfg_ref is the live Config object so baud/port changes take effect on reconnect.
    """
    ser  = None
    port = None

    while not stop_event.is_set():
        if ser is None:
            candidates = _find_port(cfg_ref.port)
            for candidate in candidates:
                try:
                    ser  = serial.Serial(candidate, cfg_ref.baud_rate, timeout=0.02)
                    port = candidate
                    t0   = time.perf_counter()
                    bus.clear(t0)
                    print(f"[sensor] connected on {port}")
                    break
                except (serial.SerialException, OSError):
                    pass
            if ser is None:
                time.sleep(0.5)
                continue

        try:
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            if resp:
                raw_val = int(resp.split()[0], 16)
                mm_raw  = interpolate(raw_val)
                if mm_raw is not None:
                    mm = mm_raw - cfg_ref.zero_offset
                    bus.push(time.perf_counter(), mm, raw_val)
        except (serial.SerialException, OSError, ValueError):
            print(f"[sensor] disconnected from {port}.")
            bus.set_connected(False)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(0.5)
