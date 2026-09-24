#!/usr/bin/env python3
"""
pico_pc.py - Full-rate LX3302A monitor with the DECODE DONE ON THE PC.

The Pico does NO decoding: its PIO times every falling-to-falling gap and it just
forwards the raw gap counts over USB as framed binary. This PC decodes the whole
stream in real time (numpy), so we keep the sensor at full ~1500 fps AND see every
frame -- instead of the Pico's ~400/s ceiling.

Because each gap count IS elapsed time (0.25 us/count), the PC reconstructs the TRUE
timestamp of every frame -> the trace has a faithful time axis (not synthetic).

  Main panel : lift height vs device-time (cm / counts)
  Dashboard  : large plain LIFT HEIGHT readout + a green half-circle FREQUENCY speedometer

This is a pure VISUAL restyle of pico_pc_gauge1.py to a flat, modern Tesla-style
touchscreen UI: dark charcoal background, softly rounded "cards", crisp typography,
a clean flat green speedometer arc. All decode/IO/threading logic is identical.

Frame protocol from the Pico: [0xAA55AA55][N u16][overflow u16][N x u32 gaps].

Usage:
    python pico_pc.py                 # auto-pick port, 15 s window, maximized
    python pico_pc.py --port COM5 --window 20
    python pico_pc.py --counts        # raw 0-4095 counts
    python pico_pc.py --csv run.csv   # log device_t,pos,status
"""
import sys, time, argparse, csv, struct, threading
from collections import deque

import serial
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import MultipleLocator
from matplotlib.patches import Wedge, Circle, FancyBboxPatch

from pico_live import start_pico, pick_port

# Calibrated in-chip for 0-30 mm (IPCE, 2026-06-18). Mapping is INVERTED:
# SENT count ~3686 = 0 mm, ~444 = 30 mm. LCLMP=count@0mm, HCLMP=count@30mm.
LCLMP, HCLMP, TRAVEL_MM = 3686, 444, 30.0
SPC = 2 / 8_000_000          # seconds per gap-count (8 MHz SM, 2 cycles/count)
MAGIC = b'\xaa\x55\xaa\x55'
EXPECT_N = 64              # must match N in FWD_PROG; used to validate framing

# Pico: forward raw gaps as framed binary, flag any FIFO overflow per block.
FWD_PROG = r'''
import rp2,time,sys,array,struct
from machine import Pin,mem32
@rp2.asm_pio()
def fg():
    wait(1,pin,0)
    wait(0,pin,0)
    wrap_target()
    mov(x,invert(null))
    label("lo")
    jmp(pin,"hi")
    jmp(x_dec,"lo")
    label("hi")
    jmp(x_dec,"ck")
    label("ck")
    jmp(pin,"hi")
    in_(x,32)
    push(noblock)
    wrap()
sm=rp2.StateMachine(0,fg,freq=8000000,in_base=Pin(15),jmp_pin=Pin(15))
FD=0x50200008
N=64
buf=array.array('I',bytearray(4*N))
hb=bytearray(8)
hb[0]=0xAA;hb[1]=0x55;hb[2]=0xAA;hb[3]=0x55
w=sys.stdout.buffer.write
sm.active(1)
mem32[FD]=0x0F
while True:
    ov=mem32[FD]&0x0F
    mem32[FD]=0x0F
    for i in range(N):
        buf[i]=sm.get()
    struct.pack_into('<HH',hb,4,N,ov)
    n=w(hb)
    n=w(buf)
'''

_CRC = None
def crc_table():
    global _CRC
    if _CRC is None:
        t = []
        for n in range(16):
            c = n
            for _ in range(4):
                c = ((c << 1) ^ 0xD) & 0xF if (c & 8) else (c << 1) & 0xF
            t.append(c)
        _CRC = t
    return _CRC

def crc4(nibs):
    t = crc_table()
    c = 3
    for n in nibs:
        c = t[c ^ n]
    return c


def _load_cal():
    """Load calibration.json (next to this file) as a sorted list of (count, mm)."""
    import json, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")
    if os.path.exists(path):
        try:
            tbl = json.load(open(path))["table"]
            return sorted([(float(cnt), float(mm)) for mm, cnt in tbl])
        except Exception:
            pass
    return None


_CAL = _load_cal()   # None -> fall back to fixed clamps


def to_mm(c):
    if _CAL:                                   # piecewise-linear interpolation over cal points
        if c <= _CAL[0][0]:
            return _CAL[0][1]
        if c >= _CAL[-1][0]:
            return _CAL[-1][1]
        for i in range(len(_CAL) - 1):
            c1, m1 = _CAL[i]; c2, m2 = _CAL[i + 1]
            if c1 <= c <= c2:
                return m1 + (c - c1) / (c2 - c1) * (m2 - m1)
    return max(0.0, min(TRAVEL_MM, (c - LCLMP) / (HCLMP - LCLMP) * TRAVEL_MM))


def decode_block(gaps, t_base):
    """gaps: 1-D float array of counts. Returns (times_s, positions, statuses, ok, total)."""
    g = gaps
    thr = 1.8 * np.median(g)
    sync = np.flatnonzero(g > thr)
    ct = np.concatenate(([0.0], np.cumsum(g))) * SPC + t_base   # true time at each edge
    times, pos, stat = [], [], []
    ok = total = 0
    for k in range(len(sync) - 1):
        s, e = int(sync[k]), int(sync[k + 1])
        if e - s != 9:                       # sync + 8 nibbles
            continue
        tick = g[s] / 56.0
        nb = np.round(g[s + 1:e] / tick).astype(np.int32) - 12
        if nb.min() < 0 or nb.max() > 15:
            continue
        total += 1
        if crc4(nb[1:7].tolist()) != int(nb[7]):
            continue
        ok += 1
        times.append(ct[s])
        pos.append((int(nb[1]) << 8) | (int(nb[2]) << 4) | int(nb[3]))
        stat.append(int(nb[0]))
    dev_end = t_base + float(np.sum(g)) * SPC
    return times, pos, stat, ok, total, dev_end


# ---------------------------------------------------------------- gauge widget
class Speedometer:
    """A flat green half-circle speedometer drawn on a matplotlib axes (Tesla style).

    The arc sweeps left->right across the top half (180 deg at left to 0 deg at
    right). A faint track shows the full range; a flat green wedge with rounded
    feel fills proportional to the value, a thin needle points to it, and the
    numeric value plus a label sit in the centre. A setpoint marker can be drawn.
    """
    def __init__(self, ax, vmin, vmax, label, unit,
                 fg, muted, track, accent, glow):
        self.ax = ax
        self.vmin = float(vmin)
        self.vmax = float(vmax)
        self.unit = unit
        self.accent = accent
        self.muted = muted

        ax.set_xlim(-1.32, 1.32)
        ax.set_ylim(-0.52, 1.30)
        ax.set_aspect("equal")
        ax.axis("off")

        R_OUT, R_IN = 1.0, 0.82           # arc band radii (thin, flat band)
        cx, cy = 0.0, 0.0

        # Full-range background track (faint, flat).
        ax.add_patch(Wedge((cx, cy), R_OUT, 0, 180, width=R_OUT - R_IN,
                           facecolor=track, edgecolor="none", zorder=1))

        # Tick marks + min/max labels around the arc.
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            ang = np.radians(180 - frac * 180)
            major = frac in (0.0, 0.5, 1.0)
            x0, y0 = (R_IN - 0.02) * np.cos(ang), (R_IN - 0.02) * np.sin(ang)
            inset = 0.13 if major else 0.085
            x1, y1 = (R_IN - inset) * np.cos(ang), (R_IN - inset) * np.sin(ang)
            ax.plot([x0, x1], [y0, y1], color=muted,
                    lw=2.0 if major else 1.3, alpha=1.0 if major else 0.6,
                    solid_capstyle="round", zorder=3)
            tv = vmin + frac * (vmax - vmin)
            tl = f"{tv:.0f}" if tv >= 10 or tv == 0 else f"{tv:.1f}"
            xt, yt = (R_OUT + 0.135) * np.cos(ang), (R_OUT + 0.135) * np.sin(ang)
            ax.text(xt, yt, tl, ha="center", va="center", fontsize=10,
                    color=muted, zorder=3, clip_on=False)

        # Live green fill wedge (grows from the left end), flat with rounded look.
        self.fill = Wedge((cx, cy), R_OUT, 180, 180, width=R_OUT - R_IN,
                          facecolor=accent, edgecolor="none", zorder=2)
        ax.add_patch(self.fill)

        # Needle + hub (thin, flat).
        (self.needle,) = ax.plot([0, 0], [0, R_IN - 0.12], color=accent,
                                 lw=2.6, solid_capstyle="round", zorder=4)
        ax.add_patch(Circle((cx, cy), 0.06, facecolor=glow,
                            edgecolor=accent, lw=1.6, zorder=5))

        # Centre numeric value + unit + label below it.
        self.val_txt = ax.text(0.0, 0.40, "--", ha="center", va="center",
                               fontsize=22, fontweight="bold", color=fg, zorder=6,
                               clip_on=False)
        self.unit_txt = ax.text(0.0, 0.17, unit.upper(), ha="center", va="center",
                                fontsize=10, color=muted, zorder=6, clip_on=False)
        ax.text(0.0, -0.34, label, ha="center", va="center", fontsize=12.5,
                fontweight="bold", color=muted, zorder=6, clip_on=False)

    def set_marker(self, value, label, color):
        """Draw a fixed setpoint indicator (redline-style) at `value` on the arc."""
        v = max(self.vmin, min(self.vmax, value))
        frac = (v - self.vmin) / (self.vmax - self.vmin) if self.vmax > self.vmin else 0.0
        ang = np.radians(180 - frac * 180)
        # contrasting radial tick spanning the arc band
        x0, y0 = 0.78 * np.cos(ang), 0.78 * np.sin(ang)
        x1, y1 = 1.04 * np.cos(ang), 1.04 * np.sin(ang)
        self.ax.plot([x0, x1], [y0, y1], color=color, lw=3.4,
                     solid_capstyle="round", zorder=5)
        # small label placed well outside the numeric tick labels so it never overlaps
        xt, yt = 1.31 * np.cos(ang), 1.31 * np.sin(ang)
        self.ax.text(xt, yt, label, ha="center", va="center", fontsize=9.5,
                     fontweight="bold", color=color, zorder=5, clip_on=False)

    def set(self, value, text=None):
        v = max(self.vmin, min(self.vmax, value))
        frac = (v - self.vmin) / (self.vmax - self.vmin) if self.vmax > self.vmin else 0.0
        # Arc fills from 180 deg (left) toward 0 deg (right) as value increases.
        end = 180.0
        start = 180.0 - frac * 180.0
        self.fill.set_theta1(start)
        self.fill.set_theta2(end)
        ang = np.radians(180 - frac * 180)
        self.needle.set_data([0, 0.64 * np.cos(ang)], [0, 0.64 * np.sin(ang)])
        self.val_txt.set_text(text if text is not None else f"{value:.0f}")

    @property
    def artists(self):
        return (self.fill, self.needle, self.val_txt)


# ------------------------------------------------------------ card helper
def add_card(fig, x, y, w, h, facecolor, edgecolor, radius=0.020, lw=1.2, zorder=0):
    """Draw a flat, softly-rounded background card (figure coords) Tesla style."""
    card = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=lw,
        mutation_aspect=fig.get_figheight() / fig.get_figwidth(),
        transform=fig.transFigure, zorder=zorder, clip_on=False,
    )
    fig.patches.append(card)
    return card


def main():
    # Cleaner, modern Helvetica-like typeface everywhere (gauges, readouts, ticks),
    # with a graceful fallback if Nimbus Sans isn't installed.
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Nimbus Sans", "DejaVu Sans"]

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--window", type=float, default=15.0)
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--no-max", action="store_true")
    ap.add_argument("--decimate", type=int, default=10,
                    help="plot every Nth frame (display only; capture/CSV stay full-rate)")
    ap.add_argument("--interval", type=int, default=33, help="redraw period in ms (~30 fps)")
    ap.add_argument("--set-freq", type=float, default=500.0,
                    help="configured SENT rate (Hz) -- shown as a setpoint marker on the freq gauge")
    args = ap.parse_args()
    DEC = max(1, args.decimate)

    port = args.port or pick_port()
    if not port:
        print("No serial port found."); sys.exit(1)
    ser = serial.Serial(port, 115200, timeout=1)
    print(f"Connecting to Pico on {port} ... (close the plot window to quit)")
    start_pico(ser, FWD_PROG)

    writer = None; fcsv = None
    if args.csv:
        fcsv = open(args.csv, "w", newline="")
        writer = csv.writer(fcsv); writer.writerow(["device_t", "pos", "status"])

    lock = threading.Lock()
    # bound plotted points to ~one window's worth so render cost stays constant over time
    plot_max = int(args.window * 1700 / DEC * 1.3) + 200
    ts = deque(maxlen=plot_max)
    ys = deque(maxlen=plot_max)
    fs = deque(maxlen=plot_max)
    stat = {"fps": 0, "crc": 0.0, "loss": 0.0, "pos": 0, "status": 0, "dev": 0.0}
    stop = threading.Event()

    def reader():
        bufb = b''
        dev_t = 0.0
        ok_acc = tot_acc = 0
        t_stream = win_t = time.perf_counter()
        win_frames = 0
        dec_i = 0
        while not stop.is_set():
            try:
                # grab whatever is buffered RIGHT NOW (don't wait for a big chunk -> low latency)
                navail = ser.in_waiting
                bufb += ser.read(navail) if navail else ser.read(1)
            except Exception:
                break
            while True:
                i = bufb.find(MAGIC)
                if i < 0:
                    bufb = bufb[-3:]                 # keep tail in case magic is split
                    break
                if len(bufb) - i < 8:
                    bufb = bufb[i:]
                    break
                N, ov = struct.unpack_from('<HH', bufb, i + 4)
                if N != EXPECT_N:                    # false / misaligned magic -> resync
                    bufb = bufb[i + 1:]
                    continue
                need = 8 + 4 * N
                if len(bufb) - i < need:
                    bufb = bufb[i:]
                    break
                raw = np.frombuffer(bufb, dtype='<u4', count=N, offset=i + 8).astype(np.float64)
                gaps = 4294967295.0 - raw      # SM forwards (0xFFFFFFFF - count); invert here
                bufb = bufb[i + need:]
                times, pos, stt, ok, tot, dev_t = decode_block(gaps, dev_t)
                ok_acc += ok; tot_acc += tot; win_frames += len(pos)
                with lock:
                    now = time.perf_counter()
                    if now - win_t >= 0.5:
                        stat["fps"] = int(win_frames / (now - win_t))
                        stat["crc"] = 100.0 * ok_acc / tot_acc if tot_acc else 0.0
                        elapsed = now - t_stream
                        stat["loss"] = max(0.0, 100.0 * (1 - dev_t / elapsed)) if elapsed > 0 else 0.0
                        win_t = now; win_frames = 0; ok_acc = tot_acc = 0
                    cur_fps = stat["fps"]
                    for tt, p, sv in zip(times, pos, stt):     # decimate: plot every DEC-th frame
                        dec_i += 1
                        if dec_i % DEC == 0:
                            ts.append(tt)
                            # store CENTIMETERS (mm/10) unless raw counts requested
                            ys.append(p if args.counts else to_mm(p) / 10.0)
                            fs.append(cur_fps)
                    if pos:
                        stat["pos"], stat["status"], stat["dev"] = pos[-1], stt[-1], dev_t
                if writer:
                    for tt, p, sv in zip(times, pos, stt):
                        writer.writerow([f"{tt:.6f}", p, sv])

    th = threading.Thread(target=reader, daemon=True); th.start()

    # ---------------------------------------------------------------- styling
    # Flat modern Tesla touchscreen palette: charcoal cards on near-black.
    BG      = "#15161a"   # figure background (deep charcoal)
    PANEL   = "#1f2228"   # card background (slightly lighter charcoal)
    BORDER  = "#33383f"   # subtle card border (a touch more contrast)
    GRID    = "#6b7280"   # gridline tint (used at low alpha)
    FG      = "#f6f7f9"   # primary text (near white)
    MUTED   = "#8e949e"   # secondary / label text (grey)
    ACCENT  = "#30d158"   # Apple/Tesla-ish green accent (trace + arc)
    GREEN   = "#30d158"   # gauge green fill / needle
    GLOW    = "#143a20"   # dark-green hub fill
    TRACK   = "#2a2f37"   # gauge background track
    AMBER   = "#ffb340"   # setpoint / "ok" warning
    RED     = "#ff453a"   # bad CRC

    plt.rcParams.update({
        "figure.facecolor":  BG,
        "axes.facecolor":    PANEL,
        "axes.edgecolor":    BORDER,
        "axes.labelcolor":   FG,
        "xtick.color":       MUTED,
        "ytick.color":       MUTED,
        "text.color":        FG,
    })

    fig = plt.figure(figsize=(14, 8))
    # Left column = two stacked time plots (lift height over velocity, shared X);
    # right column = readout + frequency gauge + quality strip.
    gs = fig.add_gridspec(3, 2, width_ratios=[4, 1.3], height_ratios=[0.85, 1.4, 0.42],
                          left=0.072, right=0.962, top=0.83, bottom=0.118,
                          wspace=0.14, hspace=0.34)
    left_gs = gs[:, 0].subgridspec(2, 1, height_ratios=[2.0, 1.15], hspace=0.10)
    ax    = fig.add_subplot(left_gs[0])              # lift height vs time
    ax_v  = fig.add_subplot(left_gs[1], sharex=ax)   # velocity vs time (shared X)
    ax_g2 = fig.add_subplot(gs[0:2, 1])    # frequency gauge (spans top of right column)
    ax_q  = fig.add_subplot(gs[2, 1])      # quality strip

    # ---- Tesla-style rounded background cards, sized to hug the content so they sit
    # cleanly BEHIND it (never overlapping/covering the plots or readouts).
    def _card(a, padx=0.017, pady=0.016):
        p = a.get_position()
        add_card(fig, p.x0 - padx, p.y0 - pady, p.width + 2 * padx, p.height + 2 * pady,
                 PANEL, BORDER, radius=0.020, zorder=0)

    def _card_group(axes, padx=0.017, pady=0.016):
        ps = [a.get_position() for a in axes]
        x0 = min(p.x0 for p in ps); y0 = min(p.y0 for p in ps)
        x1 = max(p.x1 for p in ps); y1 = max(p.y1 for p in ps)
        add_card(fig, x0 - padx, y0 - pady, (x1 - x0) + 2 * padx, (y1 - y0) + 2 * pady,
                 PANEL, BORDER, radius=0.020, zorder=0)

    _card_group([ax, ax_v])            # one card behind the stacked height + velocity plots
    for a in (ax_g2, ax_q):
        _card(a)

    # The two time plots keep the card colour; the readout axes are transparent so the
    # card shows through cleanly. Force all axes ABOVE the cards.
    ax.set_facecolor(PANEL)
    ax_v.set_facecolor(PANEL)
    for a in (ax_g2, ax_q):
        a.set_facecolor("none")
        a.patch.set_alpha(0.0)
    for a in (ax, ax_v, ax_g2, ax_q):
        a.set_zorder(3)

    (lp,) = ax.plot([], [], lw=2.4, color=ACCENT, solid_capstyle="round",
                    solid_joinstyle="round")

    if args.counts:
        ax.set_ylabel("LIFT HEIGHT (counts)", fontsize=12.5, color=MUTED,
                      fontweight="bold", labelpad=12)
        ax.set_ylim(0, 4095)
        ax.yaxis.set_major_locator(MultipleLocator(500))
        ax.yaxis.set_minor_locator(MultipleLocator(100))
        UNIT = "cts"
        POS_MAX = 4095.0
    else:
        ax.set_ylabel("LIFT HEIGHT (cm)", fontsize=12.5, color=MUTED,
                      fontweight="bold", labelpad=12)
        ax.set_ylim(0, 2.6)                                  # covers the 25.4 mm / 1-inch range
        ax.yaxis.set_major_locator(MultipleLocator(0.5))    # major every 0.5 cm
        ax.yaxis.set_minor_locator(MultipleLocator(0.1))    # faint minor every 1 mm
        UNIT = "cm"
        POS_MAX = 2.6

    # Fixed rolling-window X axis: newest sample is pinned to the right edge and data
    # scrolls left. Keeping the axis FIXED (not re-set every frame) is what lets us
    # blit -- the grid/ticks become part of the cached background.
    ax.set_xlim(0, args.window)
    ax.xaxis.set_minor_locator(MultipleLocator(0.5))

    # subtle / low-contrast flat gridlines
    ax.grid(which="major", color=GRID, alpha=0.18, lw=0.7)
    ax.grid(which="minor", color=GRID, alpha=0.07, lw=0.5)
    # large, legible tick labels on BOTH left and right sides; the X (time) labels live
    # on the velocity panel below since they share one axis.
    ax.tick_params(which="both", length=0, labelsize=11.5, pad=7)
    ax.tick_params(axis="y", labelleft=True, labelright=True, labelsize=11.5)
    ax.tick_params(axis="x", labelbottom=False)
    # Flat card look: drop the heavy frame, keep it borderless inside the card.
    for spine in ax.spines.values():
        spine.set_visible(False)
    # live lift-height readout in the corner of the height panel (mirrors velocity, green)
    height_txt = ax.text(0.012, 0.93, f"-- {UNIT}", transform=ax.transAxes,
                         ha="left", va="top", fontsize=15, fontweight="bold",
                         color=ACCENT, zorder=6)

    # ---- velocity panel (shares the time axis with the height panel) -----------
    VELC = "#5ac8fa"   # cool blue, distinct from the green height trace
    VUNIT = "cts/s" if args.counts else "cm/s"
    ax_v.set_ylabel(f"VELOCITY ({VUNIT})", fontsize=12.5, color=MUTED,
                    fontweight="bold", labelpad=12)
    ax_v.set_xlabel("TIME (s)", fontsize=12.5, color=MUTED, fontweight="bold", labelpad=9)
    ax_v.set_ylim(-5, 5)                                  # autoscaled live in update()
    ax_v.axhline(0.0, color=MUTED, lw=1.0, alpha=0.55, zorder=2)   # zero / direction line
    ax_v.xaxis.set_minor_locator(MultipleLocator(0.5))
    ax_v.grid(which="major", color=GRID, alpha=0.18, lw=0.7)
    ax_v.grid(which="minor", color=GRID, alpha=0.07, lw=0.5)
    ax_v.tick_params(which="both", length=0, labelsize=11.5, pad=7)
    ax_v.tick_params(axis="y", labelleft=True, labelright=True, labelsize=11.5)
    for spine in ax_v.spines.values():
        spine.set_visible(False)
    (lv,) = ax_v.plot([], [], lw=2.4, color=VELC, solid_capstyle="round",
                      solid_joinstyle="round")
    # live velocity readout in the corner of the velocity panel
    vel_txt = ax_v.text(0.012, 0.93, f"-- {VUNIT}", transform=ax_v.transAxes,
                        ha="left", va="top", fontsize=15, fontweight="bold",
                        color=VELC, zorder=6)

    # ---- Title (app-style header, flat)
    fig.text(0.045, 0.948, "SQUAT  PRESS", fontsize=23,
             fontweight="bold", color=FG, ha="left", va="center")
    fig.text(0.045, 0.906, "LIFT HEIGHT  &  VELOCITY", fontsize=10.5,
             color=MUTED, ha="left", va="center")
    # small green status dot in the header
    fig.text(0.962, 0.927, "●  LIVE", fontsize=11.5, fontweight="bold",
             color=ACCENT, ha="right", va="center")

    # ---------------------------------------------------------------- gauge
    g_freq = Speedometer(ax_g2, 0, 2000, "FREQUENCY", "fps",
                         FG, MUTED, TRACK, GREEN, GLOW)
    # setpoint marker: the rate the sensor is configured at (EEPROM SENT refresh)
    if args.set_freq and args.set_freq > 0:
        g_freq.set_marker(args.set_freq, "SET", AMBER)

    # ---- quality strip: three flat stat tiles (SENT / CRC / LOSS) in one card.
    ax_q.axis("off")
    # column centres for the three tiles
    cx_sent, cx_crc, cx_loss = 0.18, 0.50, 0.82
    LBL_Y, VAL_Y = 0.76, 0.30

    ax_q.text(cx_sent, LBL_Y, "SENT", transform=ax_q.transAxes, ha="center",
              va="center", fontsize=10, fontweight="bold", color=MUTED)
    t_sent = ax_q.text(cx_sent, VAL_Y, "--", transform=ax_q.transAxes, ha="center",
                       va="center", fontsize=19, fontweight="bold", color=FG)

    ax_q.text(cx_crc, LBL_Y, "CRC", transform=ax_q.transAxes, ha="center",
              va="center", fontsize=10, fontweight="bold", color=MUTED)
    t_crc = ax_q.text(cx_crc, VAL_Y, "-- %", transform=ax_q.transAxes, ha="center",
                      va="center", fontsize=19, fontweight="bold", color=FG)

    ax_q.text(cx_loss, LBL_Y, "LOSS", transform=ax_q.transAxes, ha="center",
              va="center", fontsize=10, fontweight="bold", color=MUTED)
    t_loss = ax_q.text(cx_loss, VAL_Y, "-- %", transform=ax_q.transAxes,
                       ha="center", va="center", fontsize=19, fontweight="bold",
                       color=FG)
    # faint vertical dividers between tiles
    for xd in (0.34, 0.66):
        ax_q.plot([xd, xd], [0.16, 0.84], transform=ax_q.transAxes,
                  color=BORDER, lw=1.0, zorder=1)

    if not args.no_max:
        try:
            fig.canvas.manager.window.state("zoomed")
        except Exception:
            pass

    # ---- manual blitting: only the moving artists (traces, readouts, gauge fill/needle)
    # repaint each frame; the grid, gauge dial, cards, titles and tick labels live in a
    # cached background. This is dramatically lighter than redrawing the whole canvas.
    dynamic = [lp, lv, height_txt, vel_txt,
               g_freq.fill, g_freq.needle, g_freq.val_txt,
               t_sent, t_crc, t_loss]
    for art in dynamic:
        art.set_animated(True)          # excluded from canvas.draw(); we draw them by hand

    state = {"bg": None, "vlim": 5.0}   # cached background + remembered velocity scale

    def _invalidate(_evt=None):
        state["bg"] = None              # window resized -> rebuild the cached background
    fig.canvas.mpl_connect("resize_event", _invalidate)

    def update_frame(*_):
        with lock:
            x = list(ts); yp = list(ys); s = dict(stat)
        if not x:
            return
        now = x[-1]
        xa = np.asarray(x, dtype=float)
        xr = xa - now + args.window      # newest -> right edge (= window); older scrolls left
        ya = np.asarray(yp, dtype=float)
        lp.set_data(xr, ya)

        need_full = state["bg"] is None

        # ---- velocity = smoothed time-derivative of lift height
        if xa.size >= 5:
            k = min(15, xa.size if xa.size % 2 == 1 else xa.size - 1)
            ya_s = np.convolve(ya, np.ones(k) / k, mode="same") if k >= 3 else ya
            vv = np.gradient(ya_s, xa)                     # cm/s (or cts/s)
            if vv.size >= 11:
                vv = np.convolve(vv, np.ones(11) / 11, mode="same")   # tame noise -> clean thin line
            lv.set_data(xr, vv)
            target = max(2.0, float(np.nanmax(np.abs(vv))) * 1.2)
            # Rescale velocity axis only on a real change (forces a background rebuild).
            if target > state["vlim"] * 1.05 or target < state["vlim"] * 0.6:
                state["vlim"] = target
                ax_v.set_ylim(-target, target)
                need_full = True
            vel_txt.set_text(f"{float(vv[-1]):+.1f} {VUNIT}")
        else:
            lv.set_data([], [])

        # ---- live readouts
        if args.counts:
            height_txt.set_text(f"{s['pos']} {UNIT}")
        else:
            height_txt.set_text(f"{to_mm(s['pos']) / 10.0:.2f} {UNIT}")
        g_freq.set(float(s['fps']), text=f"{s['fps']}")
        t_sent.set_text(f"{s['pos']}")
        t_crc.set_text(f"{s['crc']:.1f} %")
        t_loss.set_text(f"{s['loss']:.1f} %")
        t_crc.set_color(ACCENT if s['crc'] >= 99.0 else
                        AMBER if s['crc'] >= 90.0 else RED)

        canvas = fig.canvas
        if need_full:
            canvas.draw()                                   # static scene only (animated skipped)
            state["bg"] = canvas.copy_from_bbox(fig.bbox)
        else:
            canvas.restore_region(state["bg"])
        for art in dynamic:
            art.axes.draw_artist(art)
        canvas.blit(fig.bbox)
        canvas.flush_events()

    timer = fig.canvas.new_timer(interval=args.interval)
    timer.add_callback(update_frame)
    timer.start()
    try:
        plt.show()
    finally:
        try:
            timer.stop()
        except Exception:
            pass
        stop.set()
        try:
            ser.write(b"\x03")
        except Exception:
            pass
        ser.close(); th.join(timeout=1)
        if fcsv:
            fcsv.close(); print(f"Logged to {args.csv}")


if __name__ == "__main__":
    main()
