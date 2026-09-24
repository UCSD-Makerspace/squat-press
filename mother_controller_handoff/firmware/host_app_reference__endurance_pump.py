#!/usr/bin/env python3
"""endurance_test.py  (runs on the Pi)  — SENSOR LONGEVITY / DRIFT STUDY

Runs the SAME real mouse-squat lift (σ=2, true 1× animal speed) N times, evenly spaced over
a set number of hours (e.g. 150 lifts in 4 h), unattended, and logs how the inductive
sensor's accuracy vs the independent rail-encoder reference holds up over time.

Each lift saves full RAW per-stream data (sensor ~700 Hz, rail ~100 Hz, cmd) + a per-lift row
(peak/RMS/bias error, sensor/rail peak, CRC/loss) to a self-describing session folder:
   endurance/<YYYYMMDD_HHMMSS>_<sensor>_<N>lifts_<H>hr/
       session.csv        (metadata header + one row per lift)   <- flushed after every lift
       session_meta.json  (machine-readable metadata)
       raw/liftNNNN_t0_{sensor,rail,cmd}.csv

Controls: START / STOP session, TEST LIFT (single, for setup), SET ZERO, RAIL OFFSET, ABORT.
Keeps the right-hand FREQUENCY speedometer + RAIL/SENT/CRC/LOSS tiles.
Hardware: rail = AZD-KD via SH-U10 (/dev/ttyUSB*, Modbus 1/115200/8E1); sensor = LX3302A via Pico.
"""
import sys, os, time, struct, threading, csv, statistics, datetime, json, hashlib, shutil
APP_START_WALL = datetime.datetime.now().isoformat(timespec="seconds")   # app launch time (warm-up reference)
from collections import deque
import numpy as np
import serial
from serial.tools import list_ports
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import MultipleLocator
from matplotlib.patches import Rectangle
import tkinter as tk
from pymodbus.client import ModbusSerialClient
try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pico_pc import FWD_PROG, MAGIC, EXPECT_N, decode_block, to_mm, Speedometer, add_card
from pico_clock import PICO_SKEW      # sensor master timebase = skew-corrected Pico clock
SENSOR_LAG_S = 0.008                  # LX3302A filter + SENT response delay (~8 ms); removed from the
                                      # live error trace so it shows true position error, not the delay
from pico_live import start_pico
from pump_ctl import find_pump_port, Pump   # peristaltic pump on its OWN Pico (ttyACM with stepper.py)

FPS       = 120
STRETCH   = 1.0                 # FIXED: true 1× animal speed (the actual lift, no other movements)
SPEED_CAP = 16000
ACCEL     = 40000
DIRSIGN   = +1
DT_CMD      = 0.01
LEAD_MS     = 25.0
SPEED_MARGIN = 1.3
CATCHUP_HZ_MM = 800.0
RAIL_ADDR = 1
ABS_MIN, ABS_MAX = -3.0, 50.0
# defaults for the study
DEF_LIFTS = 150
DEF_HOURS = 4.0
HERE = os.path.dirname(os.path.abspath(__file__))
ENDUR_DIR = os.path.join(HERE, "endurance")
try: os.makedirs(ENDUR_DIR, exist_ok=True)
except Exception: pass

MOUSE_DIR = os.path.join(HERE, "mouse")
def _load_mouse_profile():
    try:
        d = np.genfromtxt(os.path.join(MOUSE_DIR, "squat1_profile.csv"), delimiter=",", names=True)
        return d["t_s"].astype(float), d["lift_mm"].astype(float)
    except Exception:
        return None, None
def _load_mouse_frames():
    try:
        z = np.load(os.path.join(MOUSE_DIR, "squat1_frames.npz"))
        return z["frames"], float(z["fps"])
    except Exception:
        return None, None
prof_t, prof_y = _load_mouse_profile()
MOUSE = prof_t is not None
vid_frames, vid_fps = _load_mouse_frames()
HAVE_VIDEO = vid_frames is not None      # shown via matplotlib imshow in the grid (no PIL needed)

BG, PANEL, BORDER = "#15161a", "#23262d", "#40454d"
GRID, FG, MUTED   = "#7c8390", "#f6f7f9", "#aeb4bd"
ACCENT, ACTUAL, ERRC, AMBER, RED = "#30d158", "#5cccff", "#f6f7f9", "#ffb340", "#ff453a"
RAILC, TICKC, DIVC = "#ff8c42", "#c2c7ce", "#3f454d"
GLOW, TRACK, HOVER = "#143a20", "#2a2f37", "#2a2f37"

def split32(v):
    v &= 0xFFFFFFFF; return [(v >> 16) & 0xFFFF, v & 0xFFFF]
def s32(hi, lo):
    v = (hi << 16) | lo; return v - (1 << 32) if v >= (1 << 31) else v

ui = {"status": "set sensor name, lifts & hours — then START", "color": MUTED}
def set_status(t, c=MUTED): ui["status"] = t; ui["color"] = c

if MOUSE:
    t_pts = np.asarray(prof_t, dtype=float); y_pts = np.asarray(prof_y, dtype=float)
else:
    t_pts = np.array([0, 0.5, 1.0, 1.5, 1.83]); y_pts = np.array([0, 10, 19, 5, 0.0])
DT = 0.02

def make_traj():
    grid = np.append(np.arange(t_pts[0], t_pts[-1], DT), t_pts[-1])
    yg = np.interp(grid, t_pts, y_pts)
    t = (grid - grid[0]) * STRETCH
    sv = np.abs(np.diff(yg, prepend=yg[0])) / (DT * STRETCH)
    ss = np.clip(sv * 100.0 * 1.3, 400, SPEED_CAP).astype(int)
    return t, yg, ss, float(t[-1])
TRAJ = dict(zip(("tt", "yy", "ss", "tend"), make_traj()))

def find_rail():
    for p in list_ports.comports():
        if (p.vid == 0x10C4) or ("ttyUSB" in (p.device or "")): return p.device
    return None
def find_sensor(exclude=()):
    for p in list_ports.comports():
        d = p.device or ""
        if d in exclude: continue
        if (p.vid == 0x2E8A) or ("ttyACM" in d): return d
    return None
# PUMP = the ttyACM whose flash carries stepper.py; SENSOR = the OTHER (bare) ttyACM; RAIL = ttyUSB.
pump_port = find_pump_port()
rail_port = find_rail()
sensor_port = find_sensor(exclude=(pump_port,) if pump_port else ())
try:
    pump = Pump(pump_port) if pump_port else None     # pump.py on the Pico: 1/8 microstep, S-curve, dose by uL
except Exception:
    pump = None
pump_ok = pump is not None
pumphc = {"down": not pump_ok}          # hotplug: mark the pump down when it drops so ops skip it + a watcher reopens it
print("[endurance_pump] pump=%s (%s)  sensor=%s  rail=%s" % (
      pump_port, "OK" if pump_ok else "none", sensor_port, rail_port), flush=True)
def _new_rail_client(port):
    return ModbusSerialClient(port=port, baudrate=115200, parity="E", stopbits=1,
                              bytesize=8, timeout=0.3, retries=0)
rail = _new_rail_client(rail_port) if rail_port else None
rail_ok = bool(rail and rail.connect())
rail_bus = threading.Lock()
# hotplug resilience: if the rail drops off the USB bus (e.g. a 24 V glitch) its ops must FAST-FAIL
# instead of blocking the GUI/lift loop; the _reconnect_watch thread reopens it by content when it returns.
railhc = {"down": not rail_ok, "fails": 0}
def _rail_miss():
    railhc["fails"] += 1
    if railhc["fails"] >= 3: railhc["down"] = True         # 3 strikes -> stop hammering a vanished device
def rail_read(reg):
    if railhc["down"]: return None
    try:
        with rail_bus:
            rr = rail.read_holding_registers(reg, count=2, device_id=RAIL_ADDR)
        if rr is None or rr.isError(): _rail_miss(); return None
        railhc["fails"] = 0
        return s32(rr.registers[0], rr.registers[1])
    except Exception:
        _rail_miss(); return None
def rail_clear_stop():
    if railhc["down"]: return
    try:
        with rail_bus: rail.write_registers(0x007C, split32(0), device_id=RAIL_ADDR)
    except Exception: _rail_miss()
def rail_stop():
    if railhc["down"]: return
    try:
        with rail_bus: rail.write_registers(0x007C, split32(0x20), device_id=RAIL_ADDR)
    except Exception: _rail_miss()
def rail_move_abs(pos_mm, speed):
    if railhc["down"]: return False
    pos_mm = min(ABS_MAX, max(ABS_MIN, pos_mm))
    blk = (split32(0) + split32(1) + split32(round(pos_mm / 0.01)) + split32(int(speed)) +
           split32(ACCEL) + split32(ACCEL) + split32(1000) + split32(1))
    try:
        with rail_bus:
            return not rail.write_registers(0x0058, blk, device_id=RAIL_ADDR).isError()
    except Exception: _rail_miss(); return False
def rail_jog(delta_mm):
    if busy() or not rail_ok: return
    rail_clear_stop()
    cur = rail_read(0x00CC)
    if cur is None: set_status("rail not responding", RED); return
    rail_move_abs(cur / 100.0 + delta_mm, 300)
    set_status(f"offset {delta_mm:+.2f} mm", FG)
def rail_set_zero():
    if busy() or not rail_ok: return
    rp = rail_read(0x00CC)
    if rp is None: set_status("rail not responding", RED); return
    zero_ref["mm"] = rp / 100.0
    set_status("RAIL zeroed (readout = 0.00 here)", AMBER)
def return_home(start_mm, tol=0.15, timeout=3.0):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        if abort_evt.is_set() or stop_evt.is_set(): break
        rail_move_abs(start_mm, 1500)
        rp = rail_read(0x00CC)
        if rp is not None and abs(rp / 100.0 - start_mm) < tol: break
        time.sleep(0.05)

sensor = serial.Serial(sensor_port, 115200, timeout=1, write_timeout=2) if sensor_port else None
sens_t, sens_y = deque(maxlen=40000), deque(maxlen=40000)
cap_dev0 = [None]                       # device_t at capture start -> live trace on Pico clock
cap_off  = [0.0]                        # (pc_t of that first captured frame) − t0: anchors the LIVE sensor trace
                                        # to the SAME t0 origin the rail uses, so the two live traces don't drift
                                        # apart by the (load-dependent) latency until the first sensor block lands
latest = {"lift": None, "sent": None, "t": 0.0}
rail_pos = {"mm": None}
zero_ref = {"mm": 0.0}
if rail_ok:                                    # zero the RAIL readout to the current position at launch
    _z0 = rail_read(0x00CC)
    if _z0 is not None: zero_ref["mm"] = _z0 / 100.0
stat = {"fps": 0, "crc": 0.0, "loss": 0.0}
lock = threading.Lock()
stop_evt = threading.Event()
abort_evt = threading.Event()
capture = {"on": False}
raw_sensor = []
run = {"active": False, "t0": None, "cmd_t": [], "cmd_y": []}

def _reopen_sensor():
    """Re-find + reopen a FRESH fd for the sensor (its ACM port hops after a reboot)."""
    global sensor
    p = find_sensor(exclude=(pump_port,) if pump_port else ())
    if p:
        try: sensor.close()
        except Exception: pass
        try:
            sensor = serial.Serial(p, 115200, timeout=1, write_timeout=2); time.sleep(0.4)
            return True
        except Exception:
            return False
    return False

def _arm_sensor():
    """Reliably (re)start the sensor Pico's FWD_PROG stream and leave `sensor` on the CORRECT fd.
    Two gotchas, both learned the hard way: (1) start_pico's reboot re-enumerates and HOPS the ACM
    port, so we must reopen a fresh fd AFTER arming, not read the stale one; (2) a soft reboot does
    NOT clear a wedged PIO, so on retry we hard-reset (machine.reset) for a guaranteed-clean PIO.
    Verified: the signal + PIO are fine; this is purely about arming cleanly."""
    global sensor
    for attempt in range(1, 7):
        try: start_pico(sensor, FWD_PROG)                   # soft reboot + paste FWD_PROG
        except Exception: pass
        _reopen_sensor()                                    # reboot may have hopped the port -> fresh fd
        t0 = time.perf_counter(); seen = b''
        while time.perf_counter() - t0 < 3.0:
            try: seen += sensor.read(sensor.in_waiting or 1)
            except Exception: break
            if MAGIC in seen:
                print("[endurance_pump] sensor streaming (arm attempt %d)" % attempt, flush=True)
                return True
        time.sleep(0.4)
    print("[endurance_pump] sensor did NOT arm after 6 tries", flush=True)
    return False

def sensor_reader():
    if not sensor: return
    _arm_sensor()
    bufb = b''; dev_t = 0.0
    ok_acc = tot_acc = win_frames = 0
    t_stream = win_t = time.perf_counter()
    last_good = time.perf_counter(); last_rearm = 0.0    # stall watchdog: auto re-arm if the stream dies/degrades
    while not stop_evt.is_set():
        try:
            n = sensor.in_waiting
            bufb += sensor.read(n) if n else sensor.read(1)
        except Exception:
            time.sleep(0.1)                             # read failing (device dropped?) -> fall through to the watchdog
        while True:
            i = bufb.find(MAGIC)
            if i < 0: bufb = bufb[-3:]; break
            if len(bufb) - i < 8: bufb = bufb[i:]; break
            N, ov = struct.unpack_from('<HH', bufb, i + 4)
            if N != EXPECT_N: bufb = bufb[i + 1:]; continue
            need = 8 + 4 * N
            if len(bufb) - i < need: bufb = bufb[i:]; break
            raw = np.frombuffer(bufb, dtype='<u4', count=N, offset=i + 8).astype(np.float64)
            gaps = 4294967295.0 - raw; bufb = bufb[i + need:]
            times, pos, stt, ok, tot, dev_t = decode_block(gaps, dev_t)
            ok_acc += ok; tot_acc += tot; win_frames += len(pos)
            now = time.perf_counter()
            with lock:
                if capture["on"] and pos:
                    for k in range(len(pos)):
                        raw_sensor.append((times[k], now, int(pos[k]), int(stt[k])))
                if now - win_t >= 0.5:
                    stat["fps"] = int(win_frames / (now - win_t))
                    stat["crc"] = 100.0 * ok_acc / tot_acc if tot_acc else 0.0
                    el = now - t_stream
                    stat["loss"] = max(0.0, 100.0 * (1 - dev_t / el)) if el > 0 else 0.0
                    win_t = now; win_frames = 0; ok_acc = tot_acc = 0
                if pos:
                    last_good = now                     # a valid frame arrived -> feed the stall watchdog
                    cnt = int(pos[-1]); latest.update(sent=cnt, lift=to_mm(cnt), t=now)
                    # LIVE trace on perf_counter RELATIVE to the rail's t0 -> one shared clock+origin with the
                    # rail (cmd_t is also now-t0), so the two traces can't drift apart and the error stays flat
                    # (drift-fix 2026-08-31). Dwell/trigger use time DIFFERENCES (shift-invariant), so the dose
                    # rule and the dwell band are unchanged; saved raw data is untouched.
                    sens_t.append((now - run["t0"]) if run["t0"] is not None else 0.0); sens_y.append(latest["lift"])
        _now = time.perf_counter()                      # STALL WATCHDOG (runs each read cycle)
        if _now - last_good > 3.0 and _now - last_rearm > 6.0:   # no valid frame for 3 s -> stream dead/degraded
            last_rearm = _now
            try: set_status("sensor stalled — auto re-arming", AMBER)
            except Exception: pass
            try: _arm_sensor()                          # reopen-by-content + restart the stream (what a manual reset did)
            except Exception: pass
            bufb = b''; dev_t = 0.0; ok_acc = tot_acc = win_frames = 0
            t_stream = win_t = last_good = time.perf_counter()
    try: sensor.write(b"\x03")
    except Exception: pass
threading.Thread(target=sensor_reader, daemon=True).start()

def _write_raw(out_dir, runid, t0, rs, rr, rc):
    base = os.path.join(out_dir, f"{runid}_t0")
    try:
        with open(base + "_sensor.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["device_t_s", "pc_t_s", "raw_count", "lift_mm", "status"])
            for dt, pt, cnt, sttv in rs:
                w.writerow([round(dt, 6), round(pt - t0, 6), cnt, round(to_mm(cnt), 4), sttv])
        with open(base + "_rail.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pc_t_s", "read_t0_s", "read_t1_s", "read_win_ms", "raw_reg_0x00CC", "rail_mm"])
            for t_rd0, t_rd1, reg in rr:                    # pc_t_s = read MIDPOINT; window bounds bracket the latency
                w.writerow([round(0.5 * (t_rd0 + t_rd1) - t0, 6), round(t_rd0 - t0, 6), round(t_rd1 - t0, 6),
                            round((t_rd1 - t_rd0) * 1000.0, 3), reg,
                            round(DIRSIGN * (reg / 100.0 - zero_ref["mm"]), 3)])
        with open(base + "_cmd.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["pc_t_s", "target_mm", "speed_hz"])
            for pt, tp, spd in rc:
                w.writerow([round(pt - t0, 6), round(tp, 4), spd])
        return len(rs), len(rr)
    except Exception as e:
        set_status(f"raw save failed: {e}", RED); return 0, 0

def _play_one(start_mm, label, runid, out_dir):
    """One lift. Streams the profile, captures raw + trace, writes raw files. Returns a stats dict or None."""
    tt_, yy_, ss_, tend_ = TRAJ["tt"], TRAJ["yy"], TRAJ["ss"], TRAJ["tend"]
    raw_rail, raw_cmd = [], []
    with lock:
        run.update(t0=time.perf_counter(), cmd_t=[], cmd_y=[], active=True)
        sens_t.clear(); sens_y.clear(); raw_sensor.clear(); cap_dev0[0] = None; cap_off[0] = 0.0; capture["on"] = True
    set_status(label, AMBER)
    t0 = run["t0"]
    vv_ = np.abs(np.gradient(yy_, tt_)); lead = (LEAD_MS / 1000.0) * STRETCH; tick = 0
    # DETERMINISTIC BUS: one loop serves the shared RS-485 -> write setpoint, then read encoder at a
    # fixed phase every cycle. No async enc_reader thread -> no random read/write collisions ->
    # reproducible rail sampling. Same ~40 Hz, same total bus load.
    while not (abort_evt.is_set() or stop_evt.is_set()):
        tau = time.perf_counter() - t0
        if tau > tend_: break
        tgt_t = min(tend_, tau + lead)
        tgt_p = float(np.interp(tgt_t, tt_, yy_)); tgt_v = float(np.interp(tgt_t, tt_, vv_))
        tgt_abs = start_mm + DIRSIGN * tgt_p
        cur = rail_pos["mm"]; err = abs(tgt_abs - cur) if cur is not None else 0.0
        sp = int(min(SPEED_CAP, max(400.0, tgt_v * 100.0 * SPEED_MARGIN, err * CATCHUP_HZ_MM)))
        t_cmd = time.perf_counter(); rail_move_abs(tgt_abs, sp); raw_cmd.append((t_cmd, tgt_p, int(sp)))
        t_rd0 = time.perf_counter(); rp = rail_read(0x00CC); t_rd1 = time.perf_counter()   # BRACKET the read latency
        if rp is not None:
            rail_pos["mm"] = rp / 100.0
            with lock:
                run["cmd_t"].append(0.5 * (t_rd0 + t_rd1) - t0)     # assign the sample to the read MIDPOINT
                run["cmd_y"].append(float(DIRSIGN * (rp / 100.0 - start_mm)))
                raw_rail.append((t_rd0, t_rd1, int(rp)))
        tick += 1; nxt = t0 + tick * DT_CMD
        while time.perf_counter() < nxt and not (abort_evt.is_set() or stop_evt.is_set()):
            time.sleep(0.001)
    t1 = time.perf_counter()
    while time.perf_counter() - t1 < 0.1 and not (abort_evt.is_set() or stop_evt.is_set()):
        time.sleep(0.02)
    capture["on"] = False
    with lock:
        rsraw = list(raw_sensor); crc = stat["crc"]; loss = stat["loss"]
    n_sen, n_rail = _write_raw(out_dir, runid, t0, rsraw, raw_rail, raw_cmd)
    with lock:
        ctp = np.array(run["cmd_t"]); cy = np.array(run["cmd_y"])
    # sensor on the PICO master clock (device_t, skew-corrected); rail (pc) mapped onto it
    if len(rsraw) > 5 and len(ctp) > 2:
        sdev = np.array([r[0] for r in rsraw]); spc = np.array([r[1] for r in rsraw])
        symm = np.array([to_mm(r[2]) for r in rsraw]); d0 = sdev[0]
        sr = (sdev - d0) * PICO_SKEW
        a, b = np.polyfit(sdev - d0, spc, 1)                # pc_abs = a*(dev-d0) + b
        cr = ((ctp + t0 - b) / a) * PICO_SKEW               # rail rel-pc -> master time
        m = (sr >= cr[0]) & (sr <= cr[-1]); sr, sym = sr[m], symm[m]
        if len(sr) > 0:
            ci_raw = np.interp(sr, cr, cy); err_raw = sym - ci_raw     # zero-shift (delay-inflated) error
            # DELAY-REMOVED: the sensor trails the rail by its ~8 ms response; find the shift (0..20 ms)
            # that best aligns them (min RMS) and report the error at that alignment = true position error.
            best_lag, best_rms, best_ci = 0.0, float(np.sqrt(np.mean(err_raw ** 2))), ci_raw
            for lag_ms in range(1, 21):
                cs = np.interp(sr - lag_ms / 1000.0, cr, cy)
                r = float(np.sqrt(np.mean((sym - cs) ** 2)))
                if r < best_rms:
                    best_rms, best_lag, best_ci = r, float(lag_ms), cs
            err = sym - best_ci
            return {"peak": float(np.max(np.abs(err))), "rms": float(np.sqrt(np.mean(err ** 2))),
                    "peak_raw": float(np.max(np.abs(err_raw))), "rms_raw": float(np.sqrt(np.mean(err_raw ** 2))),
                    "bias": float(np.mean(err)), "sensor_peak": float(np.max(sym)),
                    "rail_peak": float(np.max(best_ci)), "lag": float(best_lag), "n_sen": n_sen, "n_rail": n_rail,
                    "crc": crc, "loss": loss, "trace": (sr, sym, best_ci, err)}
    return None

# ---- environment logging HOOK (wire an I2C temp/humidity sensor here) --------
def read_env():
    """Return (sensor_temp_C, ambient_temp_C, rh_pct, vsupply_V). Blank until a sensor is wired.
    TODO: read an I2C sensor (SHT31/BME280/DS18B20) on the coil + ambient; measure supply V.
    Inductive sensors drift with temperature — this MUST be populated before publishing."""
    return ("", "", "", "")

def _profile_sha1():
    try:
        with open(os.path.join(MOUSE_DIR, "squat1_profile.csv"), "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except Exception:
        return ""
try:
    import pymodbus as _pm; _PMVER = getattr(_pm, "__version__", "")
except Exception:
    _PMVER = ""

# ============================== SESSION RUNNER ==============================
sess = {"active": False, "stop": False, "i": 0, "N": 0, "hours": 0.0, "interval": 0.0,
        "sensor": "", "dir": "", "csv": "", "t_start": 0.0, "next_in": 0.0,
        "lifts": [], "rms": [], "peak": [], "done": False, "faults": 0}
def busy(): return sess["active"] or run["active"]

# ============================== PUMP (reward dosing) ==============================
# Dose µL -> revolutions via the KPMP10 manual: 5.9 mL/min @100 rpm on the 1.52 mm tube
# = 59 µL/rev (a REFERENCE; refine by weighing later). A "qualifying lift" = the sensor height
# reaches >= height_mm and dwells there >= hold_ms. TEST LIFT always doses; a SESSION doses every
# 'ratio' qualifying lifts (fixed-ratio reward, e.g. FR6). The pump is on its own ACM serial bus,
# so dosing never touches the sensor/rail timing.
PUMP_CFG = {"uL_per_rev": 12.60, "dose_uL": 15.0, "ratio": 6,
            "height_mm": 17.9, "hold_ms": 100.0, "enabled": True}
# Trigger-height ceiling for a 100 ms hold on the recorded squat is 18.8 mm (97% of its 19.41 mm
# peak). 17.9 leaves ~0.9 mm of margin: still demanding (92% of peak), but a slightly shallow or
# quicker lift still qualifies. Setting it at 18.8 would mean zero margin and frequent misses.
pump_state = {"lifts": 0, "doses": 0, "uL": 0.0, "last_t": 0.0, "busy": False, "msg": ""}

def dose_rev():
    return max(0.0, PUMP_CFG["dose_uL"]) / max(1e-6, PUMP_CFG["uL_per_rev"])

def do_dose(reason=""):
    if not pump_ok or pumphc["down"] or pump_state["busy"]: return
    rev = dose_rev()
    if rev <= 0: return
    def _d():
        pump_state["busy"] = True
        try:
            pump.ul_per_rev = PUMP_CFG["uL_per_rev"]     # keep the Pi-side calibration in sync
            pump.dose(PUMP_CFG["dose_uL"])               # dose by volume; de-energizes when done
            pump_state["doses"] += 1; pump_state["uL"] += PUMP_CFG["dose_uL"]
            pump_state["last_t"] = time.perf_counter()
            pump_state["msg"] = f"dosed {PUMP_CFG['dose_uL']:.0f} µL ({rev:.3f} rev) · {reason}"
            set_status("PUMP " + pump_state["msg"], ACTUAL)
        except Exception as e:
            pumphc["down"] = True                        # pump likely dropped off the bus -> watcher will reopen it
            pump_state["msg"] = f"dose FAILED: {e}"; set_status("PUMP " + pump_state["msg"], RED)
        finally:
            pump_state["busy"] = False
    threading.Thread(target=_d, daemon=True).start()

def on_qualifying_lift():
    pump_state["lifts"] += 1; n = pump_state["lifts"]
    if sess["active"]:
        r = max(1, int(PUMP_CFG["ratio"]))
        if n % r == 0: do_dose(f"lift {n} · FR{r}")
        else: set_status(f"qualifying lift {n} (reward every {r})", MUTED)
    else:
        do_dose("test lift")                             # a single test lift always rewards

def pump_off():
    if pump_ok:
        try: pump.off()
        except Exception: pass
        set_status("pump de-energized", MUTED)

def prime_press(_e=None):
    """PRIME button pressed -> run the pump continuously until released (hold-to-run)."""
    if not pump_ok or pumphc["down"] or pump_state["busy"]: return
    pump_state["busy"] = True
    def _go():
        try:
            pump.prime_start(100.0)
            set_status("PRIMING — release to stop", AMBER)
        except Exception as ex:
            pump_state["busy"] = False
            set_status(f"prime FAILED: {ex}", RED)
    threading.Thread(target=_go, daemon=True).start()

def prime_release(_e=None):
    """PRIME button released -> stop the continuous run and de-energize."""
    def _stop():
        try: pump.prime_stop()
        except Exception: pass
        pump_state["busy"] = False
        set_status("prime stopped", MUTED)
    threading.Thread(target=_stop, daemon=True).start()

def _dwell_now(sr, syv, H):
    """Duration of the CURRENT unbroken run above H, measured from the SENSOR's own timestamps,
    with the entry crossing linearly interpolated between samples. 0.0 if not currently above H.

    This is what makes the rule deterministic. Timing the dwell with a polling stopwatch starts
    the clock whenever the thread happens to look -- always LATE -- so a lift that genuinely met
    'held >= 100 ms' could be measured as 98 ms and wrongly rejected. The sensor timestamps are
    the ground truth the rule is defined on, so the rule is applied to them directly.
    """
    n = len(syv)
    if n < 2 or syv[-1] < H:
        return 0.0
    i = n - 1
    while i > 0 and syv[i - 1] >= H:                 # walk back to the start of this run
        i -= 1
    if i > 0:                                        # interpolate where it actually crossed H
        y0, y1 = syv[i - 1], syv[i]
        tc = sr[i - 1] + ((H - y0) / (y1 - y0) if y1 != y0 else 0.0) * (sr[i] - sr[i - 1])
    else:
        tc = sr[0]
    return sr[-1] - tc


def trigger_watcher():
    """Once per played lift, fire on_qualifying_lift() when the SENSOR trace satisfies
    'height >= height_mm sustained for >= hold_ms'.

    The rule is evaluated on the SAME sensor samples the on-screen dwell readout uses, so the
    display and the decision can never disagree. Two passes guarantee it is never missed:
      * live  -- fires the moment the current run reaches hold_ms
      * final -- when the lift ends, re-checks the completed run, so a run that crossed the
                 threshold and finished BETWEEN polls still triggers (slightly late, but the
                 rule is honoured). If the data satisfies the rule, the dose happens. Full stop.
    """
    last_t0 = None; fired = False; was_active = False
    while not stop_evt.is_set():
        armed = PUMP_CFG["enabled"] and pump_ok and not pumphc["down"]
        active = run["active"]
        if armed and active:
            t0 = run["t0"]
            if t0 != last_t0:                        # new lift -> re-arm the per-lift latch
                last_t0 = t0; fired = False
            if not fired:
                with lock:
                    sx = list(sens_t); sy = list(sens_y)
                if _dwell_now(sx, sy, PUMP_CFG["height_mm"]) >= PUMP_CFG["hold_ms"] / 1000.0:
                    fired = True; on_qualifying_lift()
            was_active = True
            time.sleep(0.003)
            continue
        if was_active and armed and not fired:       # lift just ended -> final adjudication
            with lock:
                sx = list(sens_t); sy = list(sens_y)
            r = _dwell_run(sx, sy, PUMP_CFG["height_mm"]) if len(sx) > 2 else None
            if r and (r[1] - r[0]) >= PUMP_CFG["hold_ms"] / 1000.0:
                fired = True; on_qualifying_lift()
        was_active = active
        time.sleep(0.02)
if pump_ok:
    threading.Thread(target=trigger_watcher, daemon=True).start()

def _reconnect_watch():
    """A device that dropped off the USB bus must not wedge the run. rail/pump ops fast-fail while
    'down'; this reopens them BY CONTENT (never a fixed port) as soon as they re-enumerate."""
    global rail, rail_ok, pump, pump_ok
    while not stop_evt.is_set():
        time.sleep(3.0)
        if railhc["down"]:                              # rail (ttyUSB) dropped -> try to reopen + verify a read
            try:
                p = find_rail()
                if p:
                    c = _new_rail_client(p); ok = False
                    if c.connect():
                        rr = c.read_holding_registers(0x00CC, count=2, device_id=RAIL_ADDR)
                        ok = rr is not None and not rr.isError()
                    if ok:
                        with rail_bus:
                            try:
                                if rail: rail.close()
                            except Exception: pass
                            rail = c
                        rail_ok = True; railhc["fails"] = 0; railhc["down"] = False
                        set_status("rail reconnected", ACCENT)
                    else:
                        try: c.close()
                        except Exception: pass
            except Exception: pass
        if pumphc["down"] and not pump_state["busy"] and not run["active"]:   # pump (ttyACM) dropped -> reopen
            try:
                try:
                    if pump: pump.close()
                except Exception: pass
                pp = find_pump_port(exclude=(sensor_port,))     # exclude sensor -> never Ctrl-C the streaming sensor Pico
                if pp:
                    pump = Pump(pp); pump.ul_per_rev = PUMP_CFG["uL_per_rev"]
                    pump_ok = True; pumphc["down"] = False
                    set_status("pump reconnected", ACCENT)
            except Exception: pass
threading.Thread(target=_reconnect_watch, daemon=True).start()

SESS_COLS = ["lift", "datetime", "elapsed_s", "peak_err_mm", "rms_err_mm", "peak_raw_mm", "rms_raw_mm", "bias_mm",
             "sensor_peak_mm", "rail_peak_mm", "lag_ms", "rail_home_mm",
             "sensor_temp_C", "ambient_temp_C", "rh_pct", "vsupply_V",
             "crc_pct", "loss_pct", "n_sensor", "n_rail", "note"]

def start_session():
    if busy() or not rail_ok:
        if not rail_ok: set_status("NO RAIL LINK on /dev/ttyUSB*", RED)
        return
    try:
        N = max(1, int(float(lifts_var.get()))); H = max(0.001, float(hours_var.get()))
    except Exception:
        set_status("bad lifts/hours — enter numbers", RED); return
    sensor_name = (sensor_var.get().strip() or "sensor").replace(",", " ").replace("/", "-")[:32]
    interval = (H * 3600.0) / N
    sess.update(stop=False, i=0, N=N, hours=H, interval=interval, sensor=sensor_name,
                lifts=[], rms=[], peak=[], done=False, faults=0, next_in=0.0)
    abort_evt.clear()
    threading.Thread(target=_session_thread, daemon=True).start()
def stop_session():
    sess["stop"] = True; set_status("stopping session after this lift…", AMBER)
def do_abort():
    abort_evt.set(); sess["stop"] = True; rail_stop(); set_status("ABORTED — STOP asserted", RED)

def _session_thread():
    try:
        rail_clear_stop()
        start = rail_read(0x00CC)
        if start is None: set_status("rail not responding (power / RS-485?)", RED); return
        start_mm = start / 100.0
        peak_target = start_mm + DIRSIGN * float(y_pts.max())
        if not (ABS_MIN <= start_mm <= ABS_MAX and ABS_MIN <= peak_target <= ABS_MAX):
            set_status(f"UNSAFE: {start_mm:.1f}->{peak_target:.1f} mm out of range — SET ZERO at bottom", RED)
            return
        zero_ref["mm"] = start_mm       # RAIL readout reads 0 at the session home
        ts = datetime.datetime.now()
        sid = f"{ts:%Y%m%d_%H%M%S}_{sess['sensor']}_{sess['N']}lifts_{sess['hours']:g}hr"
        sdir = os.path.join(ENDUR_DIR, sid); rawdir = os.path.join(sdir, "raw")
        os.makedirs(rawdir, exist_ok=True)
        meta = {"session_id": sid, "datetime_start": ts.isoformat(timespec="seconds"),
                "sensor": sess["sensor"], "n_lifts": sess["N"], "duration_hr": sess["hours"],
                "interval_s": round(sess["interval"], 2), "speed": "1x animal (true mouse)",
                "profile": "squat1 mouse sigma=2 (0.5s rest + squat + 0.5s rest)",
                "profile_file": "squat1_profile.csv", "profile_sha1": _profile_sha1(),
                "profile_peak_mm": round(float(y_pts.max()), 3), "start_mm": round(start_mm, 3),
                "calibration": {"to_mm(0)": round(to_mm(0), 4), "to_mm(4095)": round(to_mm(4095), 4),
                                "file": "calibration.json (archived in this folder)"},
                "rail": "AZD-KD encoder 0x00CC (independent reference)",
                "rail_params": {"ACCEL": ACCEL, "SPEED_CAP": SPEED_CAP, "LEAD_MS": LEAD_MS,
                                "SPEED_MARGIN": SPEED_MARGIN, "DT_CMD": DT_CMD, "DIRSIGN": DIRSIGN,
                                "CATCHUP_HZ_MM": CATCHUP_HZ_MM},
                "rates_hz": {"sensor_native": "~714", "rail_reference": "~36 (Modbus during motion)"},
                "clock_note": "Pico device clock ~0.9% slow vs PC; align on one clock for lag",
                "sensor_config": {"chip_id": 6880, "sent_refresh_hz": 500, "sent_tick_us": 6, "wdscale": 2,
                                  "source": "IPCE EEPROM", "note": "the reported latency IS this SENT config - CONFIRM per sensor"},
                "app_start_wall": APP_START_WALL,
                "warmup_note": "app_start_wall = app launch (warm-up proxy if left powered); STILL record hardware power-on time separately",
                "env_note": "temperature/humidity/supply NOT logged yet - wire a sensor into read_env()",
                "pymodbus": _PMVER, "host": os.uname().nodename}
        with open(os.path.join(sdir, "session_meta.json"), "w") as f: json.dump(meta, f, indent=2)
        try: shutil.copy(os.path.join(HERE, "calibration.json"), os.path.join(sdir, "calibration.json"))
        except Exception: pass
        cpath = os.path.join(sdir, "session.csv")
        with open(cpath, "w", newline="") as f:
            w = csv.writer(f)
            for k, v in meta.items():
                if not isinstance(v, dict): w.writerow([f"# {k}", v])
            w.writerow([f"# calibration", json.dumps(meta["calibration"])])
            w.writerow(SESS_COLS)
        sess.update(active=True, dir=sdir, csv=cpath, t_start=time.perf_counter())
        set_status(f"SESSION START · {sess['N']} lifts · every {sess['interval']:.0f}s · {sess['sensor']}", ACCENT)

        for i in range(sess["N"]):
            if abort_evt.is_set() or stop_evt.is_set() or sess["stop"]: break
            sched = sess["t_start"] + i * sess["interval"]
            while time.perf_counter() < sched:                     # wait (interruptible) for the slot
                if abort_evt.is_set() or stop_evt.is_set() or sess["stop"]: break
                sess["next_in"] = sched - time.perf_counter()
                set_status(f"waiting · lift {i+1}/{sess['N']} in {sess['next_in']:.0f}s · {sess['sensor']}", MUTED)
                time.sleep(0.25)
            if abort_evt.is_set() or stop_evt.is_set() or sess["stop"]: break
            al = rail_read(0x0080)                                  # driver alarm? stop the session safely
            if al: set_status(f"RAIL ALARM {al} — session stopped at lift {i+1}", RED); break
            rail_clear_stop()
            lt = datetime.datetime.now()
            res = _play_one(start_mm, f"LIFT {i+1}/{sess['N']} · {sess['sensor']}",
                            f"lift{i+1:04d}", rawdir)
            with lock: run["active"] = False
            return_home(start_mm)
            hp = rail_read(0x00CC); rail_home = round(DIRSIGN * (hp / 100.0 - zero_ref["mm"]), 3) if hp is not None else ""   # reference-drift control (0 = returned to session home)
            st_t, amb_t, rh, vsup = read_env()                                                   # env hooks (blank until wired)
            elapsed = time.perf_counter() - sess["t_start"]
            iso = lt.isoformat(timespec="seconds")
            if res is None:
                sess["faults"] += 1
                row = [i + 1, iso, round(elapsed, 1), "", "", "", "", "", "", "", "", rail_home,
                       st_t, amb_t, rh, vsup, "", "", "", "", "FAULT(no trace)"]
            else:
                row = [i + 1, iso, round(elapsed, 1),
                       round(res["peak"], 4), round(res["rms"], 4),
                       round(res["peak_raw"], 4), round(res["rms_raw"], 4), round(res["bias"], 4),
                       round(res["sensor_peak"], 3), round(res["rail_peak"], 3),
                       round(res["lag"], 1), rail_home, st_t, amb_t, rh, vsup,
                       round(res["crc"], 1), round(res["loss"], 1), res["n_sen"], res["n_rail"], ""]
                sess["lifts"].append(i + 1); sess["rms"].append(res["rms"]); sess["peak"].append(res["peak"])
            try:
                with open(sess["csv"], "a", newline="") as f:      # flush after EVERY lift (crash-safe)
                    csv.writer(f).writerow(row)
            except Exception: pass
            sess["i"] = i + 1
        sess["done"] = True
        rms = np.array(sess["rms"])
        msg = (f"SESSION DONE · {sess['i']}/{sess['N']} lifts · {sess['sensor']}"
               + (f" · RMS {rms.mean():.3f}±{rms.std():.3f}mm" if len(rms) else "")
               + (f" · {sess['faults']} faults" if sess["faults"] else ""))
        set_status(msg, ACCENT if not sess["faults"] else AMBER)
    finally:
        with lock: run["active"] = False
        sess["active"] = False

# TEST LIFT — single lift for setup/alignment (saved under endurance/_test/)
def test_lift():
    if busy() or not rail_ok:
        if not rail_ok: set_status("NO RAIL LINK on /dev/ttyUSB*", RED)
        return
    abort_evt.clear()
    def _t():
        try:
            rail_clear_stop(); start = rail_read(0x00CC)
            if start is None: set_status("rail not responding", RED); return
            start_mm = start / 100.0
            if not (ABS_MIN <= start_mm + DIRSIGN * float(y_pts.max()) <= ABS_MAX):
                set_status("UNSAFE range — SET ZERO at bottom", RED); return
            zero_ref["mm"] = start_mm        # RAIL readout reads 0 at home for the test lift
            td = os.path.join(ENDUR_DIR, "_test"); os.makedirs(td, exist_ok=True)
            res = _play_one(start_mm, "TEST LIFT…", datetime.datetime.now().strftime("%H%M%S"), td)
            with lock: run["active"] = False
            return_home(start_mm)
            if res: set_status(f"TEST LIFT · peak {res['peak']:.2f} rms {res['rms']:.2f}mm (delay-removed; raw {res['rms_raw']:.2f}) · lag {res['lag']:.0f}ms · bias {res['bias']:+.2f}", ACCENT)
        finally:
            with lock: run["active"] = False
    threading.Thread(target=_t, daemon=True).start()

# ============================== GUI ==============================
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Nimbus Sans", "DejaVu Sans"]
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": PANEL, "axes.edgecolor": BORDER,
                     "axes.labelcolor": FG, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": FG})
root = tk.Tk(); root.title("Squat Press — Sensor · Rail · Reward Pump"); root.configure(bg=BG)
_sw, _sh = root.winfo_screenwidth(), root.winfo_screenheight()
_ww = min(1580 if HAVE_VIDEO else 1340, _sw - 30); _wh = min(884, _sh - 70)
root.geometry(f"{_ww}x{_wh}"); root.minsize(1100, 700)
fig = Figure(figsize=(13.0, 7.6), dpi=100, facecolor=BG)
# ONE clean 2-column grid: LEFT = last-lift + drift plots; RIGHT = video + gauge + tiles stacked
gs = fig.add_gridspec(1, 2, width_ratios=[3.5, 1.5], left=0.065, right=0.965,
                      top=0.815, bottom=0.095, wspace=0.13)
gl = gs[0, 0].subgridspec(2, 1, height_ratios=[1.35, 1.0], hspace=0.34)   # lift (top) / error (bottom)
gr = gs[0, 1].subgridspec(3, 1, height_ratios=[1.55, 1.15, 0.72], hspace=0.55)
ax  = fig.add_subplot(gl[0]); axe = fig.add_subplot(gl[1], sharex=ax)
axv = fig.add_subplot(gr[0]) if HAVE_VIDEO else None
axg = fig.add_subplot(gr[1]); axq = fig.add_subplot(gr[2])

def _card(a, padx=0.015, pady=0.016):
    p = a.get_position()
    add_card(fig, p.x0 - padx, p.y0 - pady, p.width + 2 * padx, p.height + 2 * pady, PANEL, BORDER, radius=0.02, zorder=0)
_card(ax); _card(axe); _card(axg); _card(axq)
if axv is not None: _card(axv)
ax.set_facecolor(PANEL); axe.set_facecolor(PANEL)
_rax = [axg, axq] + ([axv] if axv is not None else [])
for a in _rax: a.set_facecolor("none"); a.patch.set_alpha(0.0)
for a in ([ax, axe] + _rax): a.set_zorder(3)
for a in (ax, axe):
    for spn in a.spines.values(): spn.set_visible(False)
    a.tick_params(which="both", length=0, labelsize=12, pad=6, colors=TICKC)
    a.tick_params(axis="y", labelleft=True, labelright=True)
    a.grid(which="major", color=GRID, alpha=0.32, lw=0.9)
# top-left: last lift — rail vs sensor
(l_cmd,) = ax.plot([], [], lw=5.0, color=RAILC, solid_capstyle="round", label="rail (reference)", zorder=4)
(l_sen,) = ax.plot([], [], lw=2.3, color=ACTUAL, solid_capstyle="round", label="sensor", zorder=6)
# --- trigger visualization (discreet): height line + dwell band + "held N ms" + dose marker ---
(trig_line,) = ax.plot([], [], lw=1.1, ls=(0, (6, 4)), color=MUTED, alpha=0.6, zorder=3)      # trigger-height line
trig_band = Rectangle((0, 0), 0, 1, transform=ax.get_xaxis_transform(), color=AMBER, alpha=0.13, lw=0, zorder=1)
ax.add_patch(trig_band); trig_band.set_visible(False)                                          # span held above height
# dwell readout sits at the BOTTOM (x in data, y in axes fraction) so amber text never lands on
# the orange rail trace, where it is unreadable
trig_ms_txt = ax.text(0, 0.045, "", transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                      fontsize=10, fontweight="bold", color=AMBER, zorder=7)
(trig_vline,) = ax.plot([], [], lw=1.0, ls=":", color=ACCENT, alpha=0.7, zorder=4)             # the dose instant
(trig_drop,) = ax.plot([], [], marker="v", ms=11, mec="none", color=ACCENT, zorder=8)          # the dose marker
trig_lbl = ax.text(0.012, 0.055, "", transform=ax.transAxes, ha="left", va="bottom", fontsize=9, color=MUTED, zorder=7)
# label sitting ON the threshold line, at the right-hand edge, so the dashed line is self-explanatory
# sits directly UNDER the big live lift readout (top-left) so the two read as a pair:
# current height above, trigger threshold below. Clear of the traces and of both y-axes.
trig_line_lbl = ax.text(0.012, 0.855, "", transform=ax.transAxes, ha="left", va="top",
                        fontsize=10, fontweight="bold", color=MUTED, zorder=7)
# "DOSE" caption beside the marker so the arrow needs no explaining
trig_dose_lbl = ax.text(0, 0, "", ha="center", va="bottom", fontsize=9, fontweight="bold",
                        color=ACCENT, zorder=8)
for _a in (trig_ms_txt, trig_vline, trig_drop, trig_dose_lbl): _a.set_visible(False)
ax.set_ylabel("LIFT (mm)", color=MUTED, fontsize=14, fontweight="bold", labelpad=12)
ax.set_xlim(0, TRAJ["tend"] + 0.12); ax.set_ylim(-2, float(y_pts.max()) + 3)
ax.yaxis.set_major_locator(MultipleLocator(5))
ax.tick_params(axis="x", labelbottom=False)                    # time axis is labelled on the error plot below
leg = ax.legend(loc="upper right", facecolor=PANEL, edgecolor=BORDER, labelcolor=FG, fontsize=10.5, framealpha=0.92)
leg.get_frame().set_linewidth(0.8)
lift_txt = ax.text(0.012, 0.94, "-- mm", transform=ax.transAxes, ha="left", va="top",
                   fontsize=16, fontweight="bold", color=ACTUAL, zorder=7)
# middle-left: ERROR signal (sensor − rail) over the lift — ± both sides
(l_err,) = axe.plot([], [], lw=2.0, color=ERRC, solid_capstyle="round", zorder=5)
axe.axhspan(-0.5, 0.5, color=ACCENT, alpha=0.08, zorder=0)     # ±0.5 mm tolerance band
axe.axhline(0, color=MUTED, lw=1.0, alpha=0.6)
axe.set_ylabel("ERROR (mm)", color=MUTED, fontsize=13, fontweight="bold", labelpad=10)
axe.set_xlabel("TIME (s)", color=MUTED, fontsize=12, fontweight="bold", labelpad=7)
axe.set_ylim(-1, 1)
axe.yaxis.set_major_locator(MultipleLocator(0.5)); axe.yaxis.set_minor_locator(MultipleLocator(0.1))
axe.xaxis.set_minor_locator(MultipleLocator(0.1))
axe.grid(which="major", color=MUTED, alpha=0.18, lw=0.6)
axe.grid(which="minor", color=MUTED, alpha=0.08, lw=0.4)

fig.text(0.070, 0.955, "SENSOR  ENDURANCE  —  SQUAT DRIFT STUDY", color=FG, fontsize=22, fontweight="bold", va="center")
prog_txt = fig.text(0.070, 0.900, "idle — configure and START", color=MUTED, fontsize=12.5, va="center")
live_txt = fig.text(0.930, 0.955, "●  LIVE", color=ACCENT, fontsize=13, fontweight="bold", ha="right", va="center")

g_freq = Speedometer(axg, 0, 2000, "FREQUENCY", "fps", FG, MUTED, TRACK, ACCENT, GLOW)
axq.axis("off"); cx = (0.135, 0.38, 0.625, 0.87)
for x, lab in zip(cx, ("RAIL mm", "SENT", "CRC", "LOSS")):
    axq.text(x, 0.66, lab, transform=axq.transAxes, ha="center", va="center", fontsize=11, fontweight="bold", color=MUTED)
t_rail = axq.text(cx[0], 0.34, "--", transform=axq.transAxes, ha="center", va="center", fontsize=18, fontweight="bold", color=ACCENT)
t_sent = axq.text(cx[1], 0.34, "--", transform=axq.transAxes, ha="center", va="center", fontsize=18, fontweight="bold", color=FG)
t_crc  = axq.text(cx[2], 0.34, "--", transform=axq.transAxes, ha="center", va="center", fontsize=18, fontweight="bold", color=FG)
t_loss = axq.text(cx[3], 0.34, "--", transform=axq.transAxes, ha="center", va="center", fontsize=18, fontweight="bold", color=FG)
for xd in (0.258, 0.503, 0.748): axq.plot([xd, xd], [0.22, 0.78], transform=axq.transAxes, color=DIVC, lw=1.3)
# video lives IN the grid (top-right) as an image axis -> one unified layout, no separate panel
vim = None; vcap = None
if axv is not None:
    axv.axis("off")
    vim = axv.imshow(vid_frames[0], aspect="auto", zorder=4)
    axv.set_title("MOUSE  SQUAT", color=FG, fontsize=12.5, fontweight="bold", pad=5)
    vcap = axv.text(0.5, 0.05, "lift 0.0 mm", transform=axv.transAxes, ha="center", va="bottom",
                    color=FG, fontsize=11, fontweight="bold", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.25", fc=BG, ec="none", alpha=0.55))
if HAVE_VIDEO:
    _pk_i = int(np.argmax(prof_y)); _PEAK = float(prof_y.max())
    _rise_l = prof_y[:_pk_i + 1]; _rise_f = np.arange(_pk_i + 1, dtype=float)
    _fall_l = prof_y[_pk_i:][::-1]; _fall_f = np.arange(_pk_i, len(prof_y), dtype=float)[::-1]
    _f2v = (len(vid_frames) - 1) / max(1, len(prof_y) - 1)
vid_state = {"i": -1}; vsync = {"t0": None, "phase": "rise", "maxl": 0.0}
canvas = FigureCanvasTkAgg(fig, master=root); canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

tk.Frame(root, bg=BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)
bar = tk.Frame(root, bg=PANEL); bar.pack(side=tk.BOTTOM, fill=tk.X, ipady=8)
def mkbtn(parent, txt, cmd, fg, ipadx=12, sz=12, fill=False, padx=5):
    bg0 = fg if fill else PANEL
    fg0 = "#0c2a14" if fill else fg
    hov = "#3ee066" if fill else HOVER
    b = tk.Button(parent, text=txt, command=cmd, bg=bg0, fg=fg0, activebackground=hov,
                  activeforeground=fg0, relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                  font=("DejaVu Sans", sz, "bold"))
    b.bind("<Enter>", lambda e: b.config(bg=hov)); b.bind("<Leave>", lambda e: b.config(bg=bg0))
    b.pack(side=tk.LEFT, padx=padx, ipadx=ipadx, ipady=7); return b
def vsep():
    tk.Frame(bar, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=9, pady=7)
def mkentry(parent, label, var, w):
    fr = tk.Frame(parent, bg=PANEL); fr.pack(side=tk.LEFT, padx=(8, 2))
    tk.Label(fr, text=label, bg=PANEL, fg=MUTED, font=("DejaVu Sans", 8, "bold")).pack()
    tk.Entry(fr, textvariable=var, width=w, bg=TRACK, fg=FG, insertbackground=FG, relief="flat",
             justify="center", font=("DejaVu Sans", 11)).pack(ipady=3)
sensor_var = tk.StringVar(value=""); lifts_var = tk.StringVar(value=str(DEF_LIFTS)); hours_var = tk.StringVar(value=str(DEF_HOURS))
mkentry(bar, "sensor name", sensor_var, 14); mkentry(bar, "lifts", lifts_var, 5); mkentry(bar, "hours", hours_var, 5)
vsep()
mkbtn(bar, "START  SESSION", start_session, ACCENT, fill=True)
mkbtn(bar, "STOP", stop_session, AMBER, ipadx=8)
mkbtn(bar, "TEST LIFT", test_lift, MUTED, ipadx=8, sz=11)
mkbtn(bar, "ABORT", do_abort, RED, ipadx=8, padx=(16, 5))
vsep()
mkbtn(bar, "SET ZERO", rail_set_zero, AMBER, ipadx=8, sz=11)
jf = tk.Frame(bar, bg=PANEL); jf.pack(side=tk.LEFT, padx=8)
tk.Label(jf, text="RAIL OFFSET", bg=PANEL, fg=MUTED, font=("DejaVu Sans", 8, "bold")).pack()
jg = tk.Frame(jf, bg=PANEL); jg.pack()
for txt, dmm in (("−1", -1.0), ("−0.1", -0.1), ("+0.1", +0.1), ("+1", +1.0)):
    b = tk.Button(jg, text=txt, command=lambda d=dmm: rail_jog(DIRSIGN * d), bg=PANEL, fg=ACTUAL,
                  activebackground=HOVER, activeforeground=ACTUAL, relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2", font=("DejaVu Sans", 10, "bold"))
    b.bind("<Enter>", lambda e, w=b: w.config(bg=HOVER)); b.bind("<Leave>", lambda e, w=b: w.config(bg=PANEL))
    b.pack(side=tk.LEFT, padx=2, ipadx=5, ipady=3)
status = tk.Label(bar, text=ui["status"], bg=PANEL, fg=MUTED, font=("DejaVu Sans", 12)); status.pack(side=tk.RIGHT, padx=14)

# ---- PUMP: second control row (config pocket + manual dispense) ----
pbar = tk.Frame(root, bg=PANEL); pbar.pack(side=tk.BOTTOM, fill=tk.X, ipady=5)
tk.Frame(root, bg=BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)          # divider above the pump row
dose_var  = tk.StringVar(value=str(int(PUMP_CFG["dose_uL"])))
ratio_var = tk.StringVar(value=str(int(PUMP_CFG["ratio"])))
thmm_var  = tk.StringVar(value=str(PUMP_CFG["height_mm"]))
hold_var  = tk.StringVar(value=str(int(PUMP_CFG["hold_ms"])))
tk.Label(pbar, text="PUMP", bg=PANEL, fg=ACTUAL, font=("DejaVu Sans", 11, "bold")).pack(side=tk.LEFT, padx=(14, 4))
mkentry(pbar, "dose µL", dose_var, 5)
mkentry(pbar, "reward every", ratio_var, 4)
mkentry(pbar, "trig height mm", thmm_var, 5)
mkentry(pbar, "hold ms", hold_var, 5)
def apply_pump_cfg():
    try:
        PUMP_CFG["dose_uL"]   = float(dose_var.get())
        PUMP_CFG["ratio"]     = max(1, int(float(ratio_var.get())))
        PUMP_CFG["height_mm"] = float(thmm_var.get())
        PUMP_CFG["hold_ms"]   = float(hold_var.get())
        set_status(f"pump cfg · {PUMP_CFG['dose_uL']:.0f}µL={dose_rev():.3f}rev · every {PUMP_CFG['ratio']}"
                   f" · trig ≥{PUMP_CFG['height_mm']:.1f}mm held {PUMP_CFG['hold_ms']:.0f}ms", ACCENT)
    except Exception as e:
        set_status(f"bad pump cfg: {e}", RED)
mkbtn(pbar, "APPLY", apply_pump_cfg, AMBER, ipadx=8, sz=11)
mkbtn(pbar, "DISPENSE", lambda: do_dose("manual"), ACTUAL, ipadx=10, sz=11)
mkbtn(pbar, "PUMP OFF", pump_off, MUTED, ipadx=8, sz=10)
_prime_btn = mkbtn(pbar, "PRIME (hold)", (lambda: None), ACCENT, ipadx=8, sz=10)
_prime_btn.bind("<ButtonPress-1>", prime_press)     # hold to run continuously...
_prime_btn.bind("<ButtonRelease-1>", prime_release)  # ...release (even off-button) to stop
def toggle_pump():
    PUMP_CFG["enabled"] = not PUMP_CFG["enabled"]
    _pump_en_btn.config(text="AUTO: ON" if PUMP_CFG["enabled"] else "AUTO: OFF",
                        fg=ACCENT if PUMP_CFG["enabled"] else MUTED)
    set_status(f"auto-dose {'ARMED' if PUMP_CFG['enabled'] else 'disabled'}", AMBER)
_pump_en_btn = mkbtn(pbar, "AUTO: ON", toggle_pump, ACCENT, ipadx=8, sz=10)
pump_lbl = tk.Label(pbar, text="pump --", bg=PANEL, fg=MUTED, font=("DejaVu Sans", 11)); pump_lbl.pack(side=tk.RIGHT, padx=14)
if not pump_ok:
    pump_lbl.config(text="pump OFFLINE (no stepper.py Pico on ttyACM*)", fg=RED)

if not rail_ok:
    set_status("rail not found on /dev/ttyUSB* — sensor live; move SH-U10 to Pi to run", RED)

def _hms(s):
    s = max(0, int(s)); return f"{s//3600:d}:{(s%3600)//60:02d}:{s%60:02d}"
# --- manual blitting: during a lift, redraw ONLY the moving trace over a cached background
# (~1-3ms GIL/frame vs ~20ms full render) so the motion loop's rail reads stay evenly spaced.
# Safe here because the axes are FIXED (no scrolling) and the video is frozen during a lift.
_BLIT_ART = ([l_cmd, l_sen, lift_txt, l_err, trig_line, trig_line_lbl, trig_band, trig_ms_txt,
              trig_vline, trig_drop, trig_dose_lbl]
             + ([vim, vcap] if vim is not None else []))   # +trigger viz + video, all animated via cheap blit
_blit = {"bg": None, "armed": False}
canvas.mpl_connect("resize_event", lambda _e: _blit.update(bg=None))   # resize -> rebuild bg
def _dwell_run(sr, syv, H):
    """Longest contiguous (t_start, t_end) where syv >= H, else None."""
    best = None; i = 0; n = len(syv)
    while i < n:
        if syv[i] >= H:
            j = i
            while j < n and syv[j] >= H: j += 1
            if best is None or (sr[j - 1] - sr[i]) > (best[1] - best[0]): best = (sr[i], sr[j - 1])
            i = j
        else:
            i += 1
    return best

def _update_trig_viz(sx, sy):
    """Draw the trigger height line, the dwell-above-height band, its ms count, and the dose mark."""
    H = PUMP_CFG["height_mm"]; holds = PUMP_CFG["hold_ms"] / 1000.0
    x0, x1 = ax.get_xlim(); y1 = ax.get_ylim()[1]
    trig_line.set_data([x0, x1], [H, H])
    trig_line_lbl.set_text(f"trigger  {H:.1f} mm")     # .1f: 18.8 was rounding to "19" and looked wrong
    trig_lbl.set_text("")   # caption dropped: it collided with the axes, and the pump row already shows the rule
    r = _dwell_run(sx, sy, H) if (sx is not None and len(sx) > 2) else None
    if not r:
        for a in (trig_band, trig_ms_txt, trig_vline, trig_drop, trig_dose_lbl): a.set_visible(False)
        return
    t0c, t1c = r; dwell = max(0.0, t1c - t0c); met = dwell >= holds
    col = ACCENT if met else AMBER                       # amber = arming, green = hold met -> dose
    trig_band.set_x(t0c); trig_band.set_width(max(1e-3, dwell)); trig_band.set_color(col); trig_band.set_visible(True)
    # one decimal: rounding to whole ms hid the boundary case -- a 99.6 ms dwell printed as
    # "held 100 ms" while correctly FAILING the >= 100 ms test, which looked like a bug
    trig_ms_txt.set_position(((t0c + t1c) / 2.0, 0.045))
    trig_ms_txt.set_text(f"held {dwell * 1000:.1f} ms  /  {PUMP_CFG['hold_ms']:.0f} needed")
    trig_ms_txt.set_color(col); trig_ms_txt.set_visible(True)
    if met:
        tf = t0c + holds                                 # the instant the hold is satisfied -> reward
        trig_vline.set_data([tf, tf], [H, y1]); trig_vline.set_visible(True)
        trig_drop.set_data([tf], [y1 * 0.94]); trig_drop.set_visible(True)
        trig_dose_lbl.set_position((tf, y1 * 0.955)); trig_dose_lbl.set_text("DOSE")
        trig_dose_lbl.set_visible(True)
    else:
        for a in (trig_vline, trig_drop, trig_dose_lbl): a.set_visible(False)

def redraw():
    status.config(text=ui["status"], fg=ui["color"])
    if not run["active"]:
        rp = rail_read(0x00CC)
        if rp is not None: rail_pos["mm"] = rp / 100.0
    with lock:
        l, s, lt = latest["lift"], latest["sent"], latest["t"]
        fps, crc, loss = stat["fps"], stat["crc"], stat["loss"]
        ct, cy = list(run["cmd_t"]), list(run["cmd_y"]); sx, sy, t0 = list(sens_t), list(sens_y), run["t0"]
    live = (l is not None) and (time.perf_counter() - lt < 1.0)
    live_txt.set_text("●  LIVE" if live else "○  ---"); live_txt.set_color(ACCENT if live else MUTED)
    if l is not None: lift_txt.set_text(f"{l:.2f} mm")
    g_freq.set(float(fps), text=f"{fps}")
    rpm = None if rail_pos["mm"] is None else rail_pos["mm"] - zero_ref["mm"]
    t_rail.set_text("--" if rpm is None else f"{rpm:.2f}")
    t_sent.set_text("--" if s is None else f"{s}"); t_crc.set_text(f"{crc:.0f}%"); t_loss.set_text(f"{loss:.0f}%")
    t_crc.set_color(ACCENT if crc >= 99 else AMBER if crc >= 90 else RED)
    t_loss.set_color(ACCENT if loss <= 1 else AMBER if loss <= 5 else RED)
    if pump_ok:                                    # pump tally + live dosing indicator
        pump_lbl.config(text=(f"pump · doses {pump_state['doses']} · {pump_state['uL']:.0f} µL"
                              f" · qual-lifts {pump_state['lifts']}"
                              + ("  ⟳ DOSING" if pump_state['busy'] else "")),
                        fg=(ACTUAL if pump_state['busy'] else (ACCENT if PUMP_CFG['enabled'] else MUTED)))
    # progress line
    if sess["active"]:
        el = time.perf_counter() - sess["t_start"]; tot = sess["hours"] * 3600.0
        nxt = f" · next in {_hms(sess['next_in'])}" if (not run["active"] and sess["next_in"] > 0) else ""
        prog_txt.set_text(f"{sess['sensor']}  ·  lift {sess['i']}/{sess['N']}  ·  {_hms(el)} / {_hms(tot)}"
                          f"  ·  every {sess['interval']:.0f}s{nxt}"
                          + (f"  ·  {sess['faults']} faults" if sess["faults"] else ""))
        prog_txt.set_color(ACCENT)
    elif sess["done"]:
        prog_txt.set_text(f"DONE · {sess['i']}/{sess['N']} lifts saved to endurance/… · {sess['sensor']}")
        prog_txt.set_color(MUTED)
    # last-lift plot + error trace (±, sensor − rail)
    if ct: l_cmd.set_data(ct, cy)
    if sx and t0 is not None:
        sr = list(sx); l_sen.set_data(sr, sy)     # sens_t is already Pico-clock, relative to lift start
        if len(sr) > 2 and len(ct) > 2:
            l_err.set_data(sr, np.array(sy) - np.interp(np.array(sr) - SENSOR_LAG_S, ct, cy))  # delay-removed (~8ms)
    _update_trig_viz(np.asarray(sx) if sx else None, np.asarray(sy) if sy else None)   # trigger height/dwell/dose viz
    # lift-driven video frame (in-grid imshow) — mouse tracks the measured lift, rests between lifts
    if vim is not None:                            # animate the mouse every frame (drawn via blit during a lift)
        fi = 0
        if run["active"] and t0 is not None:
            if vsync["t0"] != t0: vsync.update(t0=t0, phase="rise", maxl=0.0)
            cyl = cy[-1] if cy else 0.0
            vsync["maxl"] = max(vsync["maxl"], cyl)
            if vsync["phase"] == "rise" and vsync["maxl"] > 0.85 * _PEAK and cyl < vsync["maxl"] - 0.4:
                vsync["phase"] = "fall"
            idx = np.interp(cyl, _rise_l, _rise_f) if vsync["phase"] == "rise" else np.interp(cyl, _fall_l, _fall_f)
            fi = int(round(idx * _f2v))
        fi = max(0, min(len(vid_frames) - 1, fi))
        if fi != vid_state["i"]:
            vim.set_data(vid_frames[fi])
            vcap.set_text(f"lift {prof_y[min(len(prof_y)-1, int(round(fi/_f2v)))]:.1f} mm")
            vid_state["i"] = fi
    active = run["active"]
    if active and not _blit["armed"]:              # lift just started -> switch to blit mode
        for art in _BLIT_ART: art.set_animated(True)
        _blit.update(bg=None, armed=True)
    elif not active and _blit["armed"]:            # lift just ended -> back to full render
        for art in _BLIT_ART: art.set_animated(False)
        _blit.update(bg=None, armed=False)
    if active:                                     # BLIT: only the moving trace, GIL stays free for the rail read
        if _blit["bg"] is None:
            canvas.draw()                          # one-time seed per lift (animated artists excluded from bg)
            _blit["bg"] = canvas.copy_from_bbox(fig.bbox)
        canvas.restore_region(_blit["bg"])
        for art in _BLIT_ART: art.axes.draw_artist(art)
        canvas.blit(fig.bbox); canvas.flush_events()
    else:
        canvas.draw_idle()
    root.after(70 if active else 150, redraw)
redraw()

root.protocol("WM_DELETE_WINDOW", lambda: (abort_evt.set(), stop_evt.set(), sess.update(stop=True),
                                           (pump_off() if pump_ok else None), root.after(250, root.destroy)))
root.mainloop()
try: pump.close()          # de-energize the motor + close the pump serial
except Exception: pass
try: rail.close()
except Exception: pass
try: sensor.close()
except Exception: pass
