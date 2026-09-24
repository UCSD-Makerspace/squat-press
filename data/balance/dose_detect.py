#!/usr/bin/env python3
"""
dose_detect.py - shared balance reader + dose-step detector.

ONE implementation of "what counts as a dose", used by both the CLI (dose_weigh.py) and the
live view (dose_weigh_live.py). Keep it that way: if the two front ends ever disagree about a
dose, neither number is trustworthy.

Balance link (receive-only; see Downloads/files/CONTEXT.md for how this was won):
    COM8 Gearmo RS-422, 2400/7E1, balance in S.Cont + PAUSE .0.
    Needs BOTH the ~3 V receiver bias AND the inverted Rx polarity (pin 12 -> Rx-).
The regex and port settings come from that project's mettler_stream_logger.py - they took real
effort to get right, so they are copied, not re-derived.

DETECTION RULE
    A window of the last N readings is "settled" when every reading is stable (not 'D') and the
    spread is <= tol. The plateau is the window's median.
      * plateau within min_step of baseline -> the baseline FOLLOWS the plateau.
        This is what cancels evaporation: the baseline creeps along with the drift, so a slowly
        evaporating vessel never accumulates into a phantom dose.
      * plateau >= baseline + min_step     -> DOSE. A real dose lands in well under a second and
        the baseline cannot follow anything that fast - that speed difference is the whole trick.
      * plateau <= baseline - min_step     -> mass removed (spill, vessel touched). Flagged, not
        counted, re-baselined.
"""

import re
import statistics
import threading
import time
from collections import deque

import serial

# "S     2.0110 g" / "SD    2.01 g". char 1 = ident, char 2 = status (D = dynamic).
_RESULT_RE = re.compile(
    r"^(?P<ident>[S\s])(?P<status>[\sD*])\s*(?P<value>-?[\d.]+)\s+(?P<unit>\S+)\s*$"
)
_TO_GRAMS = {"g": 1.0, "mg": 1e-3}


def open_port(port, baud=2400):
    return serial.Serial(port=port, baudrate=baud, bytesize=serial.SEVENBITS,
                         parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE,
                         timeout=0.2)


def parse(line):
    """line -> (grams, stable) or None if it is not a weight line (SI / TA / banner)."""
    m = _RESULT_RE.match(line)
    if not m or m.group("unit") not in _TO_GRAMS:
        return None
    return float(m.group("value")) * _TO_GRAMS[m.group("unit")], m.group("status") != "D"


class Reader(threading.Thread):
    """Reads the S.Cont stream on a thread and hands (t, grams, stable) to a callback."""

    def __init__(self, port, on_reading):
        super().__init__(daemon=True)
        self.ser = open_port(port)
        self._cb = on_reading
        self.running = True
        self.t0 = time.monotonic()

    def run(self):
        buf = bytearray()
        while self.running:
            chunk = self.ser.read(64)
            if not chunk:
                continue
            buf += chunk
            while b"\r\n" in buf:
                raw, _, buf = buf.partition(b"\r\n")
                p = parse(raw.decode("ascii", "replace"))
                if p is not None:
                    self._cb(time.monotonic() - self.t0, p[0], p[1])

    def stop(self):
        self.running = False
        try:
            self.ser.close()
        except Exception:
            pass


class DoseDetector:
    """Feed it readings; it emits one event per settled step in mass."""

    def __init__(self, window=10, tol_mg=0.4, min_step_mg=2.0, density=1.0):
        self.window = window
        self.tol = tol_mg * 1e-3
        self.min_step = min_step_mg * 1e-3
        self.density = density

        self._win = deque(maxlen=window)
        self.baseline = None
        self.settled = False
        self.doses = []            # grams, in order
        self.events = []           # (t, plateau_g, delta_g, kind)
        self._drift_g = 0.0        # signed baseline movement while NOT dosing
        self._quiet_s = 0.0
        self._last_quiet_t = None

    # -- conversion -------------------------------------------------------------
    def to_ul(self, grams):
        """g -> uL. 1 g of a liquid at density d occupies 1/d mL = 1000/d uL."""
        return grams * 1e3 / self.density

    # -- stats ------------------------------------------------------------------
    @property
    def n(self):
        return len(self.doses)

    @property
    def mean_ul(self):
        return self.to_ul(statistics.mean(self.doses)) if self.doses else 0.0

    @property
    def sd_ul(self):
        return self.to_ul(statistics.stdev(self.doses)) if len(self.doses) > 1 else 0.0

    @property
    def cv_pct(self):
        m = self.mean_ul
        return (self.sd_ul / m * 100.0) if (m and len(self.doses) > 1) else 0.0

    @property
    def drift_mg_per_min(self):
        if self._quiet_s < 30:
            return None
        return self._drift_g * 1e3 / (self._quiet_s / 60.0)

    def true_ul_per_rev(self, expected_ul, ul_per_rev):
        """What uL/rev SHOULD have been, given what was commanded and what arrived."""
        if not (expected_ul and ul_per_rev and self.doses):
            return None
        return self.mean_ul / (expected_ul / ul_per_rev)

    # -- the detector ------------------------------------------------------------
    def push(self, t, grams, stable):
        """Returns None, or ('baseline'|'dose'|'removed', plateau_g, delta_g)."""
        self._win.append((grams, stable))
        vals = [v for v, _ in self._win]
        self.settled = (len(self._win) == self.window
                        and all(s for _, s in self._win)
                        and (max(vals) - min(vals)) <= self.tol)
        if not self.settled:
            self._last_quiet_t = None
            return None

        plateau = statistics.median(vals)

        if self.baseline is None:
            self.baseline = plateau
            self._last_quiet_t = t
            return ("baseline", plateau, 0.0)

        delta = plateau - self.baseline

        if delta >= self.min_step:
            self.doses.append(delta)
            self.events.append((t, plateau, delta, "dose"))
            self.baseline = plateau
            self._last_quiet_t = t
            return ("dose", plateau, delta)

        if delta <= -self.min_step:
            self.events.append((t, plateau, delta, "removed"))
            self.baseline = plateau
            self._last_quiet_t = t
            return ("removed", plateau, delta)

        # Slow drift: let the baseline follow, and book it as evaporation.
        if self._last_quiet_t is not None:
            self._drift_g += delta
            self._quiet_s += t - self._last_quiet_t
        self._last_quiet_t = t
        self.baseline = plateau
        return None
