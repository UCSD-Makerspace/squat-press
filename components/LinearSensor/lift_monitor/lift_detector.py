"""
lift_detector.py — state machine that watches the sensor bus and fires
lift events when a valid lift is confirmed.

States:
  IDLE        — below lift_threshold (or waiting for drop after last lift)
  ARMED       — drop after last lift confirmed, waiting for next lift
  PRE_LIFT    — above threshold, timing; pre-buffer accumulating
  CONFIRMED   — threshold held long enough; buffering peak data
  COOLDOWN    — confirmed lift emitted; waiting pellet_cooldown before re-arming

A rolling pre-buffer (ring buffer of size window_size) is kept at all
times so that when a lift is confirmed we can flush samples that were
collected before threshold was crossed.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class LiftState(Enum):
    IDLE      = auto()
    ARMED     = auto()
    PRE_LIFT  = auto()
    CONFIRMED = auto()
    COOLDOWN  = auto()


@dataclass
class LiftEvent:
    lift_number:  int
    start_time:   float          # perf_counter at first threshold crossing
    confirm_time: float          # perf_counter when duration threshold met
    end_time:     float          # perf_counter when position dropped again
    peak_mm:      float
    samples:      list           # [(rel_t, mm, raw), ...]  relative to start_time
    config_snap:  dict           # copy of config at event time
    within_cooldown: bool = False  # True if another confirmed lift was within pellet_cooldown


class LiftDetector:
    """
    Call .process(t_abs, mm, raw) from any thread.
    on_lift_confirmed(LiftEvent) is called from the same thread when a lift fires.
    """

    def __init__(self, cfg_ref, on_lift_confirmed: Callable[[LiftEvent], None]):
        self._cfg       = cfg_ref
        self._callback  = on_lift_confirmed
        self._lock      = threading.Lock()

        self._state          = LiftState.ARMED
        self._pre_buf        = deque()   # rolling ring; rebuilt when window_size changes
        self._lift_buf       = []        # samples since threshold crossed
        self._lift_start_t   = 0.0
        self._lift_start_abs = 0.0
        self._last_lift_t    = -999.0   # abs time of last confirmed lift (for cooldown)
        self._lift_count     = 0
        self._dropped        = True     # True once we've seen drop_threshold after a lift

    # ── public ────────────────────────────────────────────────────────────────

    def process(self, t_abs: float, mm: float, raw: int):
        with self._lock:
            self._tick(t_abs, mm, raw)

    def state(self) -> LiftState:
        with self._lock:
            return self._state

    def last_lift_time(self) -> float:
        with self._lock:
            return self._last_lift_t

    # ── internals ─────────────────────────────────────────────────────────────

    def _tick(self, t_abs: float, mm: float, raw: int):
        cfg = self._cfg

        # Keep pre-buffer sized to window_size
        ws = cfg.window_size
        self._pre_buf.append((t_abs, mm, raw))
        while len(self._pre_buf) > ws:
            self._pre_buf.popleft()

        s = self._state

        if s == LiftState.ARMED:
            if mm >= cfg.lift_threshold:
                self._state          = LiftState.PRE_LIFT
                self._lift_start_t   = t_abs
                self._lift_buf       = list(self._pre_buf)  # flush pre-buffer into lift_buf

        elif s == LiftState.PRE_LIFT:
            self._lift_buf.append((t_abs, mm, raw))
            if mm < cfg.lift_threshold:
                # dropped before confirming — go back to ARMED
                self._state    = LiftState.ARMED
                self._lift_buf = []
            elif (t_abs - self._lift_start_t) >= cfg.min_lift_duration:
                self._state = LiftState.CONFIRMED

        elif s == LiftState.CONFIRMED:
            self._lift_buf.append((t_abs, mm, raw))
            if mm < cfg.lift_threshold:
                # lift ended — emit event
                self._emit(t_abs)
                # transition to COOLDOWN; drop guard also required
                self._state    = LiftState.COOLDOWN
                self._dropped  = False

        elif s == LiftState.COOLDOWN:
            self._lift_buf = []
            if mm < cfg.drop_threshold:
                self._dropped = True
            cooldown_elapsed = (t_abs - self._last_lift_t) >= cfg.pellet_cooldown
            if self._dropped and cooldown_elapsed:
                self._state = LiftState.ARMED

    def _emit(self, end_t: float):
        cfg  = self._cfg
        snap = cfg.snapshot()
        self._lift_count += 1

        start_t = self._lift_start_t
        samples = [
            (round(t - start_t, 5), round(mm, 4), raw)
            for t, mm, raw in self._lift_buf
        ]
        peak_mm = max(mm for _, mm, _ in samples) if samples else 0.0

        within_cooldown = (start_t - self._last_lift_t) < cfg.pellet_cooldown
        self._last_lift_t = end_t

        event = LiftEvent(
            lift_number      = self._lift_count,
            start_time       = start_t,
            confirm_time     = start_t + cfg.min_lift_duration,
            end_time         = end_t,
            peak_mm          = peak_mm,
            samples          = samples,
            config_snap      = snap,
            within_cooldown  = within_cooldown,
        )
        # fire callback outside the lock to avoid deadlocks
        threading.Thread(target=self._callback, args=(event,), daemon=True).start()
