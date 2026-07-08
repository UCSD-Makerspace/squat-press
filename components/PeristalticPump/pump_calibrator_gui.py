#!/usr/bin/env python3
"""
Kamoer MODBUS-RTU pump driver — CALIBRATION GUI.

Exposes every writable register + coil from the driver manual so you can test
microstepping (subdivision), speed, ramp, direction, single-step jog, etc.

Safety (learned the hard way):
  * Every Modbus frame is paced >= GAP seconds (driver needs >=35ms; comms goes
    flaky WHILE the motor spins).
  * STOP is CONFIRMED: it loops (fwd off / rev off / speed 0) and reads running
    status 0x0030 until it reads 0, then reports.
  * All serial I/O runs on a worker thread -> the window never freezes, and STOP
    always gets through (it clears the queue and jumps the line).

Run:  python pump_calibrator_gui.py
Deps: pymodbus (3.x), pyserial, tkinter (ships with Python on Windows).
"""

import time
import threading
import collections
import queue
import tkinter as tk
from tkinter import ttk

from pymodbus.client import ModbusSerialClient

GAP = 0.07  # seconds between Modbus frames (>=35ms required; 70ms = safe)

# ---- register / coil map (protocol addresses, from the A3 driver manual) ------
REG_STEP_ANGLE = 0x0000  # x100 (180 = 1.8 deg)
REG_SUBDIV     = 0x0001  # microstep subdivision
REG_START_FREQ = 0x0002  # Hz
REG_ACCEL_FREQ = 0x0003  # Hz
REG_PITCH_LO   = 0x0004  # pitch, 2 regs (def 100)
REG_STOP_MODE  = 0x0007  # 0 slow / 1 immediate
REG_SPEED      = 0x0008  # RPM
REG_CIRCLES_LO = 0x0009  # single-step circles, 2 regs, value = revs*100, low first
REG_DIRECTION  = 0x000B  # 0 fwd / 1 rev
REG_DEV_ID     = 0x0010  # 485 device id
REG_STATUS     = 0x0030  # running 1/0 (read only)
REG_BAUD_LO    = 0x0049  # baud, 2 regs
REG_ENABLE     = 0x004F  # 0 enable / 1 disable

COIL_SAVE      = 0x0000  # save-to-flash
COIL_FORWARD   = 0x0004  # run forward
COIL_REVERSE   = 0x0005  # run reverse
COIL_SINGLESTEP= 0x0007  # single-step jog

SUBDIV_CHOICES = [1, 2, 4, 8, 16, 32, 64, 128, 256]


# ---- thin paced wrapper around the modbus client (runs on worker thread) ------
class Bus:
    def __init__(self, client, addr, log):
        self.c = client
        self.addr = addr
        self.log = log

    def _pace(self):
        time.sleep(GAP)

    def wr_reg(self, reg, val, quiet=False):
        try:
            r = self.c.write_register(reg, int(val) & 0xFFFF, device_id=self.addr)
            ok = r is not None and not r.isError()
        except Exception as e:
            ok = False; r = e
        self._pace()
        if not quiet:
            self.log(f"W  reg 0x{reg:04X} = {val}   -> {'ok' if ok else 'FAIL'}")
        return ok

    def wr_regs(self, reg, vals, quiet=False):
        try:
            r = self.c.write_registers(reg, [int(v) & 0xFFFF for v in vals], device_id=self.addr)
            ok = r is not None and not r.isError()
        except Exception:
            ok = False
        self._pace()
        if not quiet:
            self.log(f"W  reg 0x{reg:04X} = {list(vals)}   -> {'ok' if ok else 'FAIL'}")
        return ok

    def wr_coil(self, coil, on, quiet=False):
        try:
            r = self.c.write_coil(coil, bool(on), device_id=self.addr)
            ok = r is not None and not r.isError()
        except Exception:
            ok = False
        self._pace()
        if not quiet:
            self.log(f"C  coil 0x{coil:04X} = {'ON' if on else 'OFF'}   -> {'ok' if ok else 'FAIL'}")
        return ok

    def rd_reg(self, reg, count=1, quiet=True):
        try:
            r = self.c.read_holding_registers(reg, count=count, device_id=self.addr)
            vals = list(r.registers) if (r is not None and hasattr(r, "registers")) else None
        except Exception:
            vals = None
        self._pace()
        if not quiet:
            self.log(f"R  reg 0x{reg:04X} x{count} = {vals}")
        return vals


class App:
    def __init__(self, root):
        self.root = root
        root.title("Kamoer Pump — Microstepping / Calibration")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.client = None
        self.bus = None
        self.jobs = collections.deque()
        self.jobs_lock = threading.Lock()
        self.out = queue.Queue()          # log/status messages -> GUI
        self.worker = None
        self.worker_run = False
        self._abort = threading.Event()   # lets STOP interrupt a timed dose mid-run

        self._build_ui()
        self.root.after(80, self._drain_out)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = dict(padx=4, pady=3)

        # connection row
        conn = ttk.LabelFrame(self.root, text="Connection")
        conn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        ttk.Label(conn, text="Port").grid(row=0, column=0, **pad)
        _default_port = "COM8" if sys.platform.startswith("win") else "/dev/ttyUSB0"
        self.e_port = ttk.Entry(conn, width=12); self.e_port.insert(0, _default_port); self.e_port.grid(row=0, column=1, **pad)
        ttk.Label(conn, text="Baud").grid(row=0, column=2, **pad)
        self.e_baud = ttk.Entry(conn, width=8); self.e_baud.insert(0, "9600"); self.e_baud.grid(row=0, column=3, **pad)
        ttk.Label(conn, text="Addr").grid(row=0, column=4, **pad)
        self.e_addr = ttk.Entry(conn, width=4); self.e_addr.insert(0, "1"); self.e_addr.grid(row=0, column=5, **pad)
        self.b_conn = ttk.Button(conn, text="Connect", command=self.connect); self.b_conn.grid(row=0, column=6, **pad)
        self.b_disc = ttk.Button(conn, text="Disconnect", command=self.disconnect, state="disabled"); self.b_disc.grid(row=0, column=7, **pad)
        self.lbl_conn = ttk.Label(conn, text="● offline", foreground="#b00"); self.lbl_conn.grid(row=0, column=8, **pad)

        # left: parameters
        params = ttk.LabelFrame(self.root, text="Parameters  (Set writes the register)")
        params.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        self.p = {}  # name -> (var, widget)
        r = 0
        r = self._add_combo(params, r, "Microstep / subdivision", "subdiv", SUBDIV_CHOICES, "8", REG_SUBDIV)
        r = self._add_entry(params, r, "Step angle (x100, 180=1.8°)", "step_angle", "180", REG_STEP_ANGLE)
        r = self._add_entry(params, r, "Speed (RPM)", "speed", "30", REG_SPEED)
        r = self._add_combo(params, r, "Direction", "direction", ["0 = forward", "1 = reverse"], "0 = forward", REG_DIRECTION, decode=lambda s: int(s.split()[0]))
        r = self._add_entry(params, r, "Start frequency (Hz)", "start_freq", "150", REG_START_FREQ)
        r = self._add_entry(params, r, "Accel/decel frequency (Hz)", "accel_freq", "400", REG_ACCEL_FREQ)
        r = self._add_combo(params, r, "Stop mode", "stop_mode", ["0 = slow (ramp)", "1 = immediate"], "0 = slow (ramp)", REG_STOP_MODE, decode=lambda s: int(s.split()[0]))
        r = self._add_entry(params, r, "Pitch (2 regs, def 100)", "pitch", "100", REG_PITCH_LO, is32=True)
        r = self._add_entry(params, r, "Single-step circles (revolutions)", "circles", "0.75", REG_CIRCLES_LO, is32=True, scale=100)

        ttk.Separator(params, orient="horizontal").grid(row=r, column=0, columnspan=3, sticky="ew", pady=6); r += 1
        ttk.Label(params, text="Advanced (needs Save + power-cycle):", foreground="#666").grid(row=r, column=0, columnspan=3, sticky="w", **pad); r += 1
        r = self._add_entry(params, r, "Device ID (485 addr)", "dev_id", "1", REG_DEV_ID)
        r = self._add_entry(params, r, "Baud rate (32-bit) ⚠", "baud", "9600", REG_BAUD_LO, is32=True)

        ttk.Button(params, text="Read all back", command=self.read_all).grid(row=r, column=0, columnspan=3, sticky="ew", padx=4, pady=(8, 4)); r += 1

        # dose calibration helper -------------------------------------------------
        dose = ttk.LabelFrame(self.root, text="Dose helper  (target µL ↔ revolutions)")
        dose.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        dpad = dict(padx=4, pady=3)
        ttk.Label(dose, text="Target dose (µL)").grid(row=0, column=0, sticky="w", **dpad)
        self.v_target = tk.StringVar(value="44"); ttk.Entry(dose, textvariable=self.v_target, width=8).grid(row=0, column=1, **dpad)
        ttk.Label(dose, text="Measured µL/rev").grid(row=1, column=0, sticky="w", **dpad)
        self.v_ulrev = tk.StringVar(value="59"); ttk.Entry(dose, textvariable=self.v_ulrev, width=8).grid(row=1, column=1, **dpad)
        ttk.Label(dose, text="(nominal 59 = 1.52×3.22 tube — UPDATE after weighing)",
                  foreground="#666").grid(row=1, column=2, sticky="w", **dpad)
        self.lbl_revs = ttk.Label(dose, text="→ 0.746 rev / dose", font=("Consolas", 10, "bold"))
        self.lbl_revs.grid(row=0, column=2, sticky="w", **dpad)
        ttk.Button(dose, text="Compute", command=self.compute_dose).grid(row=2, column=0, **dpad)
        ttk.Button(dose, text="→ load into Single-step circles", command=self.load_dose_into_circles).grid(row=2, column=1, columnspan=2, sticky="ew", **dpad)
        ttk.Button(dose, text="Apply full ≈44 µL preset to driver", command=self.apply_preset).grid(row=3, column=0, columnspan=3, sticky="ew", **dpad)
        ttk.Separator(dose, orient="horizontal").grid(row=4, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(dose, text="Timed dose — burst (s)").grid(row=5, column=0, sticky="w", **dpad)
        self.v_duration = tk.StringVar(value="0.75")
        ttk.Entry(dose, textvariable=self.v_duration, width=8).grid(row=5, column=1, **dpad)
        tk.Button(dose, text="▶ Run timed dose", command=self.timed_dose, bg="#1e7a34", fg="white").grid(row=5, column=2, sticky="ew", **dpad)
        ttk.Label(dose, text="(burst auto-fills from Compute using dose ÷ µL-per-rev ÷ rpm)",
                  foreground="#666").grid(row=6, column=0, columnspan=3, sticky="w", **dpad)

        # right: actions + status + log
        right = ttk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)

        act = ttk.LabelFrame(right, text="Motor actions")
        act.grid(row=0, column=0, sticky="ew")
        self.b_en  = ttk.Button(act, text="Enable motor",  command=lambda: self.enqueue(lambda b: b.wr_reg(REG_ENABLE, 0)));  self.b_en.grid(row=0, column=0, **pad)
        self.b_dis = ttk.Button(act, text="Disable motor", command=lambda: self.enqueue(lambda b: b.wr_reg(REG_ENABLE, 1))); self.b_dis.grid(row=0, column=1, **pad)
        ttk.Button(act, text="▶ Forward", command=self.run_forward).grid(row=1, column=0, sticky="ew", **pad)
        ttk.Button(act, text="◀ Reverse", command=self.run_reverse).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(act, text="Single-step (jog)", command=self.single_step).grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Button(act, text="Save to flash", command=lambda: self.enqueue(lambda b: b.wr_coil(COIL_SAVE, True))).grid(row=3, column=0, columnspan=2, sticky="ew", **pad)

        self.b_stop = tk.Button(right, text="STOP", command=self.stop, bg="#c0392b", fg="white",
                                font=("Segoe UI", 16, "bold"), height=2)
        self.b_stop.grid(row=1, column=0, sticky="ew", pady=6)

        stat = ttk.LabelFrame(right, text="Live status")
        stat.grid(row=2, column=0, sticky="ew")
        self.lbl_status = ttk.Label(stat, text="running: ?   speed: ?   subdiv: ?   dir: ?   enable: ?",
                                    font=("Consolas", 10))
        self.lbl_status.grid(row=0, column=0, sticky="w", **pad)
        self.auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(stat, text="Auto-poll (1.5s)", variable=self.auto, command=self._maybe_poll).grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(stat, text="Refresh now", command=self.poll_status).grid(row=1, column=0, sticky="e", **pad)

        logf = ttk.LabelFrame(right, text="Log")
        logf.grid(row=3, column=0, sticky="nsew", pady=6)
        self.txt = tk.Text(logf, width=52, height=14, font=("Consolas", 9))
        self.txt.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, command=self.txt.yview); sb.grid(row=0, column=1, sticky="ns")
        self.txt.config(yscrollcommand=sb.set)

        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

    def _add_entry(self, parent, r, label, name, default, reg, is32=False, scale=1):
        pad = dict(padx=4, pady=3)
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", **pad)
        var = tk.StringVar(value=default)
        ttk.Entry(parent, textvariable=var, width=10).grid(row=r, column=1, **pad)
        ttk.Button(parent, text="Set", width=5,
                   command=lambda: self._write_param(name, reg, var, is32, scale)).grid(row=r, column=2, **pad)
        self.p[name] = (var, reg, is32, scale, None)
        return r + 1

    def _add_combo(self, parent, r, label, name, values, default, reg, decode=None):
        pad = dict(padx=4, pady=3)
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", **pad)
        var = tk.StringVar(value=default)
        ttk.Combobox(parent, textvariable=var, values=[str(v) for v in values], width=12, state="readonly").grid(row=r, column=1, **pad)
        ttk.Button(parent, text="Set", width=5,
                   command=lambda: self._write_param(name, reg, var, False, 1, decode)).grid(row=r, column=2, **pad)
        self.p[name] = (var, reg, False, 1, decode)
        return r + 1

    # ---------------- actions ----------------
    def _write_param(self, name, reg, var, is32, scale, decode=None):
        if not self._check_conn():
            return
        raw = var.get().strip()
        try:
            val = decode(raw) if decode else float(raw)
        except Exception:
            self.log(f"! bad value for {name}: {raw!r}"); return
        val = int(round(val * scale)) if scale != 1 else int(val)
        if is32:
            lo, hi = val & 0xFFFF, (val >> 16) & 0xFFFF
            self.enqueue(lambda b: b.wr_regs(reg, [lo, hi]))
        else:
            self.enqueue(lambda b: b.wr_reg(reg, val))

    def run_forward(self):
        if not self._check_conn():
            return
        try:
            rpm = int(float(self.p["speed"][0].get()))
        except Exception:
            rpm = 30
        def job(b):
            b.wr_reg(REG_ENABLE, 0)
            b.wr_reg(REG_SPEED, rpm)
            b.wr_coil(COIL_FORWARD, True)
        self.enqueue(job)

    def run_reverse(self):
        if not self._check_conn():
            return
        try:
            rpm = int(float(self.p["speed"][0].get()))
        except Exception:
            rpm = 30
        def job(b):
            b.wr_reg(REG_ENABLE, 0)
            b.wr_reg(REG_SPEED, rpm)
            b.wr_coil(COIL_REVERSE, True)
        self.enqueue(job)

    def single_step(self):
        """Set circles (revolutions) then trigger single-step -> moves exactly that many revs.
        Needs a NON-ZERO speed (single-step runs at the speed register, which STOP zeroes),
        and a fresh rising edge on the trigger coil each time."""
        if not self._check_conn():
            return
        try:
            revs = float(self.p["circles"][0].get())
        except Exception:
            revs = 1.0
        try:
            rpm = int(float(self.p["speed"][0].get()))
        except Exception:
            rpm = 60
        if rpm <= 0:
            rpm = 60
        # revolutions = circles / pitch. Force pitch=100 so circles = revs*100 (per manual 2.4.4.8).
        val = int(round(revs * 100))
        lo, hi = val & 0xFFFF, (val >> 16) & 0xFFFF
        def job(b):
            b.wr_coil(COIL_SINGLESTEP, False, quiet=True)  # ensure coil low first
            b.wr_reg(REG_ENABLE, 0)                        # enable motor
            b.wr_regs(REG_PITCH_LO, [100, 0])              # pitch = 100 -> circles/100 = revolutions
            b.wr_reg(REG_SPEED, rpm)                       # runs at this speed
            b.wr_regs(REG_CIRCLES_LO, [lo, hi])            # circles = revs*100
            b.wr_coil(COIL_SINGLESTEP, True)               # MOMENTARY trigger: pulse ON ...
            b.wr_coil(COIL_SINGLESTEP, False)              # ... then OFF (self-resetting) -> one fixed move
            self.log(f"single-step: {revs} rev @ {rpm} rpm  (circles={val}, pitch=100)")
        self.enqueue(job)

    def compute_dose(self):
        """revs = target µL / measured µL-per-rev; also auto-fill the timed-burst seconds
        (burst = revs / (rpm/60)) so the timed dose matches the target volume."""
        try:
            target = float(self.v_target.get()); ulrev = float(self.v_ulrev.get())
            revs = target / ulrev
            txt = f"→ {revs:.3f} rev / dose"
            try:
                rpm = float(self.p["speed"][0].get())
                if rpm > 0:
                    dur = revs * 60.0 / rpm
                    self.v_duration.set(f"{dur:.3f}")
                    txt += f"   =  {dur:.3f} s @ {rpm:.0f} rpm"
            except Exception:
                pass
            self.lbl_revs.config(text=txt)
            return revs
        except Exception:
            self.lbl_revs.config(text="→ ? (check numbers)"); return None

    def load_dose_into_circles(self):
        revs = self.compute_dose()
        if revs is not None:
            self.p["circles"][0].set(f"{revs:.3f}")
            self.log(f"loaded {revs:.3f} rev into Single-step circles")

    def apply_preset(self):
        """Write the recommended ~44 µL dosing profile to the driver in one shot."""
        if not self._check_conn():
            return
        revs = self.compute_dose() or 0.75
        # keep whatever subdivision is in the field (MUST match your DIP) — don't clobber it
        try:
            subdiv = int(self.p["subdiv"][0].get())
        except Exception:
            subdiv = 8
        # reflect the quiet/controlled preset in the fields
        self.p["speed"][0].set("30")
        self.p["start_freq"][0].set("150")
        self.p["accel_freq"][0].set("400")
        self.p["stop_mode"][0].set("0 = slow (ramp)")
        self.p["pitch"][0].set("100")
        self.p["circles"][0].set(f"{revs:.3f}")
        val = int(round(revs * 100))
        lo, hi = val & 0xFFFF, (val >> 16) & 0xFFFF
        def job(b):
            b.wr_reg(REG_ENABLE, 0)          # enable motor
            b.wr_reg(REG_SUBDIV, subdiv)     # microstep from field (MUST match DIP SW7-9)
            b.wr_reg(REG_STEP_ANGLE, 180)    # 1.8 deg
            b.wr_regs(REG_PITCH_LO, [100, 0])# pitch 100 -> circles/100 = revs
            b.wr_reg(REG_START_FREQ, 150)    # gentle launch, no stall
            b.wr_reg(REG_ACCEL_FREQ, 400)    # smooth ramp
            b.wr_reg(REG_STOP_MODE, 0)       # slow ramp stop = quiet (count unchanged)
            b.wr_reg(REG_SPEED, 30)          # low speed = quiet + torque margin
            b.wr_regs(REG_CIRCLES_LO, [lo, hi])
            self.log(f"QUIET preset: subdiv 8, 30 rpm, start 150Hz, accel 400Hz, slow stop, {revs:.3f} rev/dose")
        self.enqueue(job)

    def timed_dose(self):
        """Deterministic dose: run Forward for exactly `Burst (s)` at the set RPM, then
        confirmed-stop. On-time is measured at the motor for reproducibility. STOP aborts it."""
        if not self._check_conn():
            return
        try:
            rpm = int(float(self.p["speed"][0].get()))
        except Exception:
            rpm = 60
        if rpm <= 0:
            rpm = 60
        try:
            dur = float(self.v_duration.get())
        except Exception:
            dur = 0.75
        dur = max(0.05, min(dur, 30.0))
        def job(b):
            self._abort.clear()
            b.wr_coil(COIL_FORWARD, False, quiet=True)
            b.wr_reg(REG_ENABLE, 0)
            b.wr_reg(REG_SPEED, rpm)
            b.wr_coil(COIL_FORWARD, True)
            t0 = time.time()
            self.log(f"timed dose: fwd {dur:.3f}s @ {rpm} rpm ...")
            while time.time() - t0 < dur and not self._abort.is_set():
                time.sleep(0.005)
            ran = time.time() - t0
            for _ in range(25):
                b.wr_coil(COIL_FORWARD, False, quiet=True)
                b.wr_coil(COIL_REVERSE, False, quiet=True)
                b.wr_reg(REG_SPEED, 0, quiet=True)
                st = b.rd_reg(REG_STATUS)
                if st is not None and st[0] == 0:
                    break
            self._abort.clear()
            self.log(f"dose done  (ran ~{ran:.3f}s, stopped){'  [ABORTED]' if self._abort.is_set() else ''}")
        self.enqueue(job)

    def stop(self):
        """CONFIRMED stop: aborts any timed dose, clears the queue, verifies status 0x0030 == 0."""
        if not self.bus:
            return
        self._abort.set()
        with self.jobs_lock:
            self.jobs.clear()
            self.jobs.appendleft(self._stop_job)

    def _stop_job(self, b):
        for _ in range(40):
            b.wr_coil(COIL_FORWARD, False, quiet=True)
            b.wr_coil(COIL_REVERSE, False, quiet=True)
            b.wr_coil(COIL_SINGLESTEP, False, quiet=True)   # also clear single-step trigger
            b.wr_reg(REG_SPEED, 0, quiet=True)
            st = b.rd_reg(REG_STATUS)
            if st is not None and st[0] == 0:
                self.log("STOP confirmed  (status 0x30 = 0)")
                self._abort.clear()
                return
        self.log("!! STOP: status not confirmed 0 — CUT POWER (hand on switch)")
        self._abort.clear()

    def read_all(self):
        if not self._check_conn():
            return
        def job(b):
            names = [("step_angle", REG_STEP_ANGLE, 1), ("subdiv", REG_SUBDIV, 1),
                     ("start_freq", REG_START_FREQ, 1), ("accel_freq", REG_ACCEL_FREQ, 1),
                     ("stop_mode", REG_STOP_MODE, 1), ("speed", REG_SPEED, 1),
                     ("direction", REG_DIRECTION, 1), ("dev_id", REG_DEV_ID, 1)]
            out = []
            for nm, reg, cnt in names:
                v = b.rd_reg(reg, cnt)
                out.append(f"{nm}={v[0] if v else '?'}")
            self.log("READ: " + "  ".join(out))
        self.enqueue(job)

    def poll_status(self):
        if not self.bus:
            return
        def job(b):
            st  = b.rd_reg(REG_STATUS)
            sp  = b.rd_reg(REG_SPEED)
            sd  = b.rd_reg(REG_SUBDIV)
            dr  = b.rd_reg(REG_DIRECTION)
            en  = b.rd_reg(REG_ENABLE)
            f = lambda v: v[0] if v else "?"
            self.out.put(("status",
                f"running: {f(st)}   speed: {f(sp)}   subdiv: {f(sd)}   dir: {f(dr)}   enable: {f(en)}"))
        self.enqueue(job)

    def _maybe_poll(self):
        if self.auto.get() and self.bus:
            self.poll_status()
            self.root.after(1500, self._maybe_poll)

    # ---------------- worker plumbing ----------------
    def enqueue(self, job):
        with self.jobs_lock:
            self.jobs.append(job)

    def _worker_loop(self):
        while self.worker_run:
            job = None
            with self.jobs_lock:
                if self.jobs:
                    job = self.jobs.popleft()
            if job is None:
                time.sleep(0.02); continue
            try:
                job(self.bus)
            except Exception as e:
                self.out.put(("log", f"! job error: {e}"))

    def _drain_out(self):
        try:
            while True:
                kind, msg = self.out.get_nowait()
                if kind == "status":
                    self.lbl_status.config(text=msg)
                else:
                    self.txt.insert("end", msg + "\n"); self.txt.see("end")
        except queue.Empty:
            pass
        self.root.after(80, self._drain_out)

    def log(self, msg):
        self.out.put(("log", msg))

    # ---------------- connection ----------------
    def _check_conn(self):
        if not self.bus:
            self.log("! not connected"); return False
        return True

    def connect(self):
        port = self.e_port.get().strip()
        try:
            baud = int(self.e_baud.get()); addr = int(self.e_addr.get())
        except Exception:
            self.log("! bad baud/addr"); return
        self.client = ModbusSerialClient(port=port, baudrate=baud, parity="N",
                                         stopbits=1, bytesize=8, timeout=0.4, retries=1)
        if not self.client.connect():
            self.log(f"! could not open {port}"); self.client = None; return
        self.bus = Bus(self.client, addr, self.log)
        self.worker_run = True
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()
        self.lbl_conn.config(text="● online", foreground="#0a0")
        self.b_conn.config(state="disabled"); self.b_disc.config(state="normal")
        self.log(f"connected {port} @ {baud} addr {addr}")
        self.poll_status()

    def disconnect(self, closing=False):
        # always try a confirmed stop first
        if self.bus:
            with self.jobs_lock:
                self.jobs.clear(); self.jobs.appendleft(self._stop_job)
            time.sleep(0.5 + 40 * 5 * GAP)  # give the confirmed-stop job time to run
        self.worker_run = False
        if self.worker:
            self.worker.join(timeout=1.0)
        if self.client:
            try: self.client.close()
            except Exception: pass
        self.client = None; self.bus = None
        if not closing:
            self.lbl_conn.config(text="● offline", foreground="#b00")
            self.b_conn.config(state="normal"); self.b_disc.config(state="disabled")
            self.log("disconnected (motor stopped)")

    def on_close(self):
        try:
            self.disconnect(closing=True)
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
