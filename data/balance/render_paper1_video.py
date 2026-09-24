#!/usr/bin/env python3
"""Two-panel timelapse of the 8-hr Paper_1 session.
TOP  = raw balance signal (mg vs h), revealed by a sweeping time cursor.
BOTTOM = the reward we care about: each dose's volume (uL) as it lands + cumulative mL.
A big elapsed clock + dose counter + cumulative total + "~Nx real time" convey the 8-hour length.

Scale integrity (verified by audit): y-axes FIXED to true units, cursor maps exactly to real elapsed
time, session cut at the first >10-min dose gap so the end-of-file bump never shows. Density stamped.

   python render_paper1_video.py            # -> Paper_1_animation.mp4 + 3 still frames
"""
import os, sys, csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
try:
    import imageio_ffmpeg
    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dose_detect import DoseDetector

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "Paper_1.csv")
D = 1.03                      # 1:1 Ensure/water mix density (g/mL) - PROVISIONAL, matches all prior
                              # Paper_1 numbers. Re-measure on the balance (the 1.1766 Ensure value
                              # looked high; that would imply ~1.088 mix). Update here + re-render.
VIDEO_SEC = 22
FPS = 30
N_FRAMES = VIDEO_SEC * FPS
C_RAW = "#3b6ea5"; C_DOSE = "#2ca25f"; C_CUM = "#1f78b4"; C_CUR = "#e05a3a"

# ---------------------------------------------------------------- load + reduce (audited correct)
t = []; m = []; st = []
for r in csv.DictReader(open(CSV)):
    t.append(float(r["elapsed_s"])); m.append(float(r["mass"])); st.append(r["stable"] == "True")
t = np.array(t); m = np.array(m)

det = DoseDetector(density=D); dose_t = []; dose_ul = []
for ti, mi, si in zip(t, m, st):
    ev = det.push(ti, mi, si)
    if ev and ev[0] == "dose" and 5 < ev[2] * 1e3 < 40:
        dose_t.append(ti); dose_ul.append(ev[2] * 1e3 / D)
dose_t = np.array(dose_t); dose_ul = np.array(dose_ul)
# drop the spurious end-of-file bump: keep the contiguous run up to the first inter-dose gap > 10 min
if len(dose_t) > 1:
    brk = np.where(np.diff(dose_t) > 600)[0]
    if len(brk):
        dose_t = dose_t[:brk[0] + 1]; dose_ul = dose_ul[:brk[0] + 1]
T_END = dose_t[-1] + 300.0
t, m = t[t <= T_END], m[t <= T_END]

STEP = max(1, len(t) // 3000)
tr = t[::STEP] / 3600.0; mr = m[::STEP] * 1e3           # hours, mg
TH = T_END / 3600.0
ratio = round(T_END / VIDEO_SEC, -2)
cum_ml = np.cumsum(dose_ul) / 1000.0

# ---------------------------------------------------------------- figure
plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(12.8, 7.2), dpi=100); fig.patch.set_facecolor("white")
gs = fig.add_gridspec(2, 1, height_ratios=[1, 1], hspace=0.30,
                      left=0.075, right=0.915, top=0.84, bottom=0.09)
ax_raw = fig.add_subplot(gs[0]); ax_rew = fig.add_subplot(gs[1])
for ax in (ax_raw, ax_rew):
    ax.grid(True, axis="y", alpha=0.15, linewidth=0.6)
    for s in ("top", "right"): ax.spines[s].set_visible(True); ax.spines[s].set_color("#ccc")

# TOP -- raw
ax_raw.set_xlim(0, TH * 1.01); ax_raw.set_ylim(0, 1600)
ax_raw.set_ylabel("mass on balance (mg)")
ax_raw.set_title("RAW BALANCE SIGNAL", loc="left", fontsize=11, color="#666", fontweight="bold", pad=7)
(raw_line,) = ax_raw.plot([], [], lw=1.1, color=C_RAW)
cur_raw = ax_raw.axvline(0, color=C_CUR, lw=1.0, alpha=0.9)

# BOTTOM -- reward (dots = uL left axis; cumulative line = mL right axis, distinct colour)
ax_rew.set_xlim(0, TH * 1.01); ax_rew.set_ylim(0, 20)
ax_rew.set_xlabel("session time (hours)"); ax_rew.set_ylabel("dose volume (µL)")
ax_rew.set_title("REWARD DELIVERED", loc="left", fontsize=11, color="#666", fontweight="bold", pad=7)
ax_rew.axhline(15, color="#c0c0c0", ls="--", lw=1)
ax_rew.text(0.99 * TH, 15.4, "15 µL target", ha="right", va="bottom", fontsize=8, color="#999")
dose_sc = ax_rew.scatter([], [], s=26, color=C_DOSE, zorder=3, edgecolor="white", linewidth=0.4,
                         label="per-dose volume (µL)")
cur_rew = ax_rew.axvline(0, color=C_CUR, lw=1.0, alpha=0.9)
ax_cum = ax_rew.twinx(); ax_cum.set_ylim(0, 1.6)
ax_cum.set_ylabel("cumulative delivered (mL)", color=C_CUM, labelpad=6)
ax_cum.tick_params(axis="y", colors=C_CUM); ax_cum.spines["right"].set_color(C_CUM)
(cum_line,) = ax_cum.plot([], [], lw=2.2, color=C_CUM, alpha=0.9, label="cumulative (mL)")
ax_rew.legend([dose_sc, cum_line], ["per-dose volume (µL)", "cumulative (mL)"],
              loc="upper left", fontsize=8, framealpha=0.9, borderpad=0.6)

# ---------------------------------------------------------------- HUD (right-aligned block)
fig.text(0.075, 0.945, "Paper_1 — 8-hour reward-pump endurance session", fontsize=15, fontweight="bold")
fig.text(0.075, 0.905, "1:1 Ensure/water · mix density %.3f g/mL · playback ≈ %d× real time"
         % (D, ratio), fontsize=9, color="#888")
clock = fig.text(0.915, 0.945, "", fontsize=15, family="monospace", fontweight="bold",
                 color="#222", ha="right")
readout = fig.text(0.915, 0.905, "", fontsize=12, family="monospace", fontweight="bold",
                   color="#177a41", ha="right")


def hms(sec):
    sec = int(sec); return "%d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def update(k):
    ct = (k / (N_FRAMES - 1)) * T_END
    hh = ct / 3600.0
    ir = np.searchsorted(tr * 3600.0, ct)
    raw_line.set_data(tr[:ir], mr[:ir])
    cur_raw.set_xdata([hh, hh]); cur_rew.set_xdata([hh, hh])
    nd = int(np.searchsorted(dose_t, ct))
    if nd:
        dose_sc.set_offsets(np.column_stack([dose_t[:nd] / 3600.0, dose_ul[:nd]]))
        cum_line.set_data(dose_t[:nd] / 3600.0, cum_ml[:nd])
    else:
        dose_sc.set_offsets(np.empty((0, 2))); cum_line.set_data([], [])
    clock.set_text("%s / %s" % (hms(ct), hms(T_END)))
    readout.set_text("dose %d / %d      total %.3f mL" % (nd, len(dose_t), cum_ml[nd - 1] if nd else 0.0))
    return raw_line, cur_raw, cur_rew, dose_sc, cum_line


anim = FuncAnimation(fig, update, frames=N_FRAMES, interval=1000 / FPS, blit=False)

for name, frac in [("start", 0.03), ("mid", 0.5), ("end", 0.99)]:
    update(int(frac * (N_FRAMES - 1)))
    fig.savefig(os.path.join(HERE, "Paper_1_frame_%s.png" % name), dpi=110)
print("saved 3 still frames")

out_mp4 = os.path.join(HERE, "Paper_1_animation.mp4")
try:
    anim.save(out_mp4, writer="ffmpeg", fps=FPS, dpi=110, savefig_kwargs={"facecolor": "white"})
    print("saved", out_mp4)
except Exception as e:
    print("ffmpeg failed (%s) -> GIF" % e)
    anim.save(os.path.join(HERE, "Paper_1_animation.gif"), writer="pillow", fps=min(FPS, 20))
