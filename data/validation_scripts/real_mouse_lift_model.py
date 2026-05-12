"""
real_mouse_lift_model.py
========================
Physics-based simulation answering:
  "What is the minimum hold time for the sensor to detect a lift event
   within +/- 0.5 mm?"

Model:
  Concentric (lift) : linear ramp at max observed velocity (step-function worst case)
                      OR scaled from video data
  Hold              : flat at peak_mm for T_hold ms
  Eccentric (drop)  : GRAVITY FREEFALL — pos(t) = peak - 0.5 * 9800 * t^2 (mm)
                      (gravity does not scale with mouse speed — it is ground truth)

Key result:
  Gravity limits the first-sample error on the descent side to 0.122 mm
  (at 5 ms sampling). This is independent of lift speed and hold time.
  Minimum hold time for ±0.5 mm detection = 0 ms.

Input:  real mouse lift v1.csv   (columns: frame, mm, 120 fps)
Output: console summary + 3-panel matplotlib figure
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
from scipy.interpolate import interp1d
import warnings
warnings.filterwarnings("ignore")

# ── Constants ─────────────────────────────────────────────────────────────────
FPS             = 120        # frames per second (video)
G_MM_S2         = 9800       # mm/s^2
DT_MS           = 5.0        # worst-case sensor sample interval (ms) — confirmed
ERROR_THRESHOLD = 0.5        # mm
CSV_FILE        = "real mouse lift v1.csv"

# Phase-offset resolution for worst-case sweep
N_OFFSETS = 500   # test 500 evenly-spaced phase offsets across one sample interval


# ── Load video data ───────────────────────────────────────────────────────────
df        = pd.read_csv(CSV_FILE)
vid_frames = df.iloc[:, 0].values.astype(float)
vid_pos    = df.iloc[:, 1].values.astype(float)

PEAK_MM    = float(vid_pos.max())
PEAK_FRAME = float(vid_frames[vid_pos.argmax()])

# Concentric phase only — up to and including the peak hold
conc_mask   = vid_frames <= PEAK_FRAME
c_times_ms  = vid_frames[conc_mask] / FPS * 1000
c_pos       = vid_pos[conc_mask]
T_LIFT_MS   = c_times_ms[-1]   # original lift duration

# Max observed lift velocity (mm/s) from inter-frame slopes
v_interp = []
for i in range(len(c_times_ms) - 2):     # exclude the flat hold at end
    dt = c_times_ms[i+1] - c_times_ms[i]
    dp = c_pos[i+1] - c_pos[i]
    if dt > 0:
        v_interp.append(abs(dp / dt))
V_MAX_MM_MS  = max(v_interp)             # mm/ms
V_MAX_MM_S   = V_MAX_MM_MS * 1000        # mm/s

conc_interp = interp1d(c_times_ms, c_pos, kind="linear",
                       bounds_error=False, fill_value=(0.0, PEAK_MM))


# ── Gravity freefall ──────────────────────────────────────────────────────────
def gravity_pos(t_after_peak_ms):
    """Position (mm) at t ms after peak under gravity freefall."""
    t_s = t_after_peak_ms / 1000.0
    return PEAK_MM - 0.5 * G_MM_S2 * t_s ** 2


# ── Build full position profile ───────────────────────────────────────────────
def build_profile(speed_scale, hold_ms, use_video_ascent=True, dt_dense_ms=0.1):
    """
    Returns (t_ms, pos_mm) dense arrays for the full lift.

    speed_scale  : <1 = faster than real mouse, >1 = slower
                   Applied to the concentric phase only.
    hold_ms      : time at peak (ms)
    use_video_ascent : True  = scale video concentric data
                       False = constant-velocity ramp at V_MAX
    """
    # Concentric
    if use_video_ascent:
        t_conc_end = T_LIFT_MS * speed_scale
        t_conc     = np.arange(0, t_conc_end, dt_dense_ms)
        pos_conc   = conc_interp(t_conc / speed_scale)
    else:
        # Step function: linear ramp at V_MAX * speed_scale (scale > 1 = faster)
        v          = V_MAX_MM_MS * speed_scale         # mm/ms
        t_conc_end = PEAK_MM / v
        t_conc     = np.arange(0, t_conc_end, dt_dense_ms)
        pos_conc   = np.clip(v * t_conc, 0, PEAK_MM)

    # Hold
    if hold_ms > 0:
        t_hold  = np.arange(dt_dense_ms, hold_ms + dt_dense_ms, dt_dense_ms)
        pos_hold = np.full_like(t_hold, PEAK_MM)
    else:
        t_hold = np.array([])
        pos_hold = np.array([])

    # Gravity descent (200 ms is more than enough to fall 19.5 mm)
    t_fall_end = np.sqrt(2 * PEAK_MM / G_MM_S2) * 1000  # ms to hit floor
    t_fall     = np.arange(dt_dense_ms, t_fall_end, dt_dense_ms)
    pos_fall   = np.maximum(gravity_pos(t_fall), 0.0)

    # Stitch together
    t_profile = np.concatenate([
        t_conc,
        t_conc[-1] + t_hold,
        t_conc[-1] + (hold_ms if hold_ms > 0 else 0) + t_fall,
    ])
    pos_profile = np.concatenate([pos_conc, pos_hold, pos_fall])
    return t_profile, pos_profile


# ── Simulate sensor sampling ──────────────────────────────────────────────────
def simulate(speed_scale, hold_ms, use_video_ascent=True):
    """
    Returns worst-case (max error) detected peak across all phase offsets.
    Also returns best-case detected peak and number of samples (at 1x scale).
    """
    t_prof, pos_prof = build_profile(speed_scale, hold_ms, use_video_ascent)
    profile_interp   = interp1d(t_prof, pos_prof, kind="linear",
                                bounds_error=False, fill_value=(0.0, 0.0))
    t_end = t_prof[-1]

    offsets = np.linspace(0, DT_MS, N_OFFSETS, endpoint=False)
    detected_peaks = []

    for offset in offsets:
        t_samp    = np.arange(offset, t_end, DT_MS)
        x_samp    = profile_interp(t_samp)
        if len(x_samp) == 0:
            continue
        detected_peaks.append(x_samp.max())

    if not detected_peaks:
        return None

    detected_peaks = np.array(detected_peaks)
    worst_detected = detected_peaks.min()   # worst-case = lowest detected peak
    best_detected  = detected_peaks.max()

    return {
        "speed_scale":      speed_scale,
        "hold_ms":          hold_ms,
        "true_peak":        PEAK_MM,
        "worst_detected":   worst_detected,
        "best_detected":    best_detected,
        "worst_error":      PEAK_MM - worst_detected,
        "best_error":       PEAK_MM - best_detected,
        "passed":           (PEAK_MM - worst_detected) <= ERROR_THRESHOLD,
        "n_samples":        int(round(t_prof[-1] / DT_MS)),
    }


# ── Console: physics summary ───────────────────────────────────────────────────
grav_drop_5ms  = 0.5 * G_MM_S2 * (DT_MS / 1000) ** 2
t_drop_thresh  = np.sqrt(2 * ERROR_THRESHOLD / G_MM_S2) * 1000

print()
print("=" * 62)
print("  MINIMUM LIFT DETECTION — PHYSICS SUMMARY")
print("=" * 62)
print(f"  Video:  {FPS} fps  |  Peak: {PEAK_MM} mm  |  Lift duration: {T_LIFT_MS:.0f} ms")
print(f"  Max observed velocity:  {V_MAX_MM_S:.1f} mm/s  "
      f"({V_MAX_MM_MS:.4f} mm/ms)")
print()
print("  Sampling")
print(f"    Worst-case interval : {DT_MS} ms")
print(f"    Detection threshold : +/-{ERROR_THRESHOLD} mm")
print()
print("  GRAVITY GUARANTEE  (descent side)")
print(f"    Drop in {DT_MS} ms          : {grav_drop_5ms:.4f} mm")
print(f"    Time to drop {ERROR_THRESHOLD} mm    : {t_drop_thresh:.1f} ms")
print(f"    --> Descent error is ALWAYS <= {grav_drop_5ms:.3f} mm")
print(f"        (first sample after peak is at most {DT_MS} ms later)")
print(f"        (gravity is {t_drop_thresh/DT_MS:.1f}x slower than sampling rate)")
print()

# Per-speed sweep at hold=0
SPEED_SCALES = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
HOLD_TIMES   = [0, 5, 10, 20, 50, 100]

print("  STEP-FUNCTION WORST CASE (hold=0 ms, linear ramp at V_max / scale)")
print(f"  {'Scale':>6}  {'V_eff(mm/s)':>11}  {'Worst error':>12}  Result")
print("  " + "-" * 45)
for sc in SPEED_SCALES:
    res = simulate(sc, hold_ms=0, use_video_ascent=False)
    v_eff = V_MAX_MM_S * sc
    flag  = "PASS" if res["passed"] else "FAIL"
    print(f"  {sc:>6.1f}x  {v_eff:>11.1f}  {res['worst_error']:>11.4f} mm  {flag}")

print()
print("  WORST-ERROR SWEEP  (step function, V_max / scale)")
header = f"  {'Hold':>6}ms  |" + "".join(f"  {sc:.0f}x" for sc in SPEED_SCALES)
print(header)
print("  " + "-" * (len(header) - 2))
for h in HOLD_TIMES:
    row = f"  {h:>8}  |"
    for sc in SPEED_SCALES:
        res = simulate(sc, hold_ms=h, use_video_ascent=False)
        flag = "P" if res["passed"] else "F"
        row += f"  {res['worst_error']:.2f}{flag}"
    print(row)

print()
print("  SENSOR FIRMWARE NOTE")
print("    No averaging/smearing observed in sensor firmware.")
print("    Readings are instantaneous ADC samples (confirmed from jitter data).")
print()


# ── Conclusion ─────────────────────────────────────────────────────────────────
print("=" * 62)
print("  CONCLUSION")
print("=" * 62)
print(f"  We will detect lift events at ANY speed within")
print(f"  +/- {grav_drop_5ms:.2f} mm of error (worst case {DT_MS:.0f} ms post-peak).")
print()
print(f"  Minimum hold time for +/-{ERROR_THRESHOLD} mm detection: 0 ms")
print(f"  (gravity-limited: {grav_drop_5ms:.3f} mm/sample on descent)")
print()
print(f"  The sampling rate would need to exceed {t_drop_thresh:.0f} ms per sample")
print(f"  before the +/-{ERROR_THRESHOLD} mm guarantee breaks.")
print(f"  Our worst-case interval is {DT_MS:.0f} ms — {t_drop_thresh/DT_MS:.1f}x inside the limit.")
print("=" * 62)
print()


# ── Figures ────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 13))
fig.patch.set_facecolor("#F8F8F8")
fig.suptitle(
    "Minimum Lift Detection Validation\n"
    "Step-function worst case  |  Gravity freefall descent  |  5 ms sampling",
    fontsize=13, fontweight="bold"
)
gs = gridspec.GridSpec(2, 3, figure=fig,
                       hspace=0.45, wspace=0.35,
                       top=0.90, bottom=0.08, left=0.07, right=0.97)

ax_slow  = fig.add_subplot(gs[0, 0])   # 1x speed profile
ax_fast  = fig.add_subplot(gs[0, 1])   # 10x speed profile
ax_grav  = fig.add_subplot(gs[0, 2])   # gravity zoom
ax_heat  = fig.add_subplot(gs[1, :2])  # error heatmap
ax_conc  = fig.add_subplot(gs[1, 2])   # video concentric vs step function

for ax in (ax_slow, ax_fast, ax_grav, ax_heat, ax_conc):
    ax.set_facecolor("#FFFFFF")
    ax.grid(True, alpha=0.22, linewidth=0.7)
    for sp in ax.spines.values():
        sp.set_linewidth(0.6)


def draw_profile_panel(ax, speed_scale, hold_ms=0, use_video=False, title=""):
    """Draw a single lift profile with sample overlay."""
    t, pos = build_profile(speed_scale, hold_ms, use_video_ascent=use_video)
    interp = interp1d(t, pos, kind="linear",
                      bounds_error=False, fill_value=(0.0, 0.0))

    ax.plot(t, pos, color="#1565C0", linewidth=1.8, label="True profile", zorder=3)

    # Shade ±ERROR_THRESHOLD around peak
    ax.axhspan(PEAK_MM - ERROR_THRESHOLD, PEAK_MM + 0.5,
               alpha=0.10, color="green", label=f"+/-{ERROR_THRESHOLD}mm window")

    # Show worst-case sampling (offset that gives lowest detected peak)
    offsets = np.linspace(0, DT_MS, N_OFFSETS, endpoint=False)
    detected = []
    for off in offsets:
        ts = np.arange(off, t[-1], DT_MS)
        xs = interp(ts)
        detected.append(xs.max())
    worst_off = offsets[np.argmin(detected)]
    t_samp    = np.arange(worst_off, t[-1], DT_MS)
    x_samp    = interp(t_samp)

    # Color each sample by proximity to peak
    colors = ["#2E7D32" if abs(x - PEAK_MM) <= ERROR_THRESHOLD else "#C62828"
              for x in x_samp]
    for xi, yi, ci in zip(t_samp, x_samp, colors):
        ax.scatter(xi, yi, s=25, color=ci, zorder=5, linewidths=0)

    # Best detected marker
    best_idx  = np.argmax(x_samp)
    best_val  = x_samp[best_idx]
    ax.scatter(t_samp[best_idx], best_val, s=80, color="#FF6F00",
               zorder=6, marker="*", label=f"Best hit: {best_val:.3f}mm")
    ax.axhline(PEAK_MM, color="gray", linewidth=0.8, linestyle="--")

    err = PEAK_MM - min(detected)
    ax.set_title(f"{title}\nWorst error: {err:.3f} mm  "
                 f"({'PASS' if err <= ERROR_THRESHOLD else 'FAIL'})",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (ms)", fontsize=8)
    ax.set_ylabel("Position (mm)", fontsize=8)
    ax.legend(fontsize=6, framealpha=0.85)
    ax.set_ylim(-0.5, PEAK_MM + 1.5)


draw_profile_panel(ax_slow, speed_scale=1.0, hold_ms=0, use_video=False,
                   title=f"1x speed  ({V_MAX_MM_S:.0f} mm/s = real mouse max, step fn)")
draw_profile_panel(ax_fast, speed_scale=10.0, hold_ms=0, use_video=False,
                   title=f"10x speed ({V_MAX_MM_S*10:.0f} mm/s, step fn, hold=0)")


# ── Gravity guarantee panel ────────────────────────────────────────────────────
t_grav_ms = np.linspace(0, 25, 500)
pos_grav  = np.maximum(gravity_pos(t_grav_ms), 0.0)

ax_grav.plot(t_grav_ms, pos_grav, color="#1565C0", linewidth=2.2,
             label="Gravity freefall")
ax_grav.axhspan(PEAK_MM - ERROR_THRESHOLD, PEAK_MM,
                alpha=0.15, color="green", label=f"+/-{ERROR_THRESHOLD}mm window")

sample_t = np.arange(0, 26, DT_MS)
sample_p = np.maximum(gravity_pos(sample_t), 0.0)
ax_grav.scatter(sample_t, sample_p, s=60, color="#FF6F00", zorder=5,
                label=f"Samples ({DT_MS:.0f}ms interval)")

for i, (ti, pi) in enumerate(zip(sample_t, sample_p)):
    err = PEAK_MM - pi
    ax_grav.annotate(f"{err:.3f}mm", (ti, pi),
                     textcoords="offset points", xytext=(4, -12),
                     fontsize=6.5, color="#333")

ax_grav.axhline(PEAK_MM, color="gray", linewidth=0.8, linestyle="--",
                label="True peak")
ax_grav.set_xlim(-1, 26)
ax_grav.set_xlabel("Time after peak (ms)", fontsize=8)
ax_grav.set_ylabel("Position (mm)", fontsize=8)
ax_grav.set_title(f"Gravity guarantee\n"
                  f"Error at t={DT_MS:.0f}ms = {grav_drop_5ms:.3f}mm  "
                  f"(<{ERROR_THRESHOLD}mm threshold)",
                  fontsize=9, fontweight="bold")
ax_grav.legend(fontsize=6.5, framealpha=0.85)


# ── Error heatmap ──────────────────────────────────────────────────────────────
HEAT_SCALES    = [1, 2, 5, 10, 20, 50, 100]
HEAT_HOLDS     = [0, 5, 10, 20, 50, 100, 200]

error_matrix = np.zeros((len(HEAT_HOLDS), len(HEAT_SCALES)))
for ri, h in enumerate(HEAT_HOLDS):
    for ci, sc in enumerate(HEAT_SCALES):
        res = simulate(sc, h, use_video_ascent=False)
        error_matrix[ri, ci] = res["worst_error"]

im = ax_heat.imshow(error_matrix, aspect="auto", cmap="RdYlGn_r",
                    vmin=0, vmax=ERROR_THRESHOLD * 1.5,
                    origin="lower")
ax_heat.set_xticks(range(len(HEAT_SCALES)))
ax_heat.set_xticklabels([f"{s}x" for s in HEAT_SCALES], fontsize=8)
ax_heat.set_yticks(range(len(HEAT_HOLDS)))
ax_heat.set_yticklabels([f"{h}ms" for h in HEAT_HOLDS], fontsize=8)
ax_heat.set_xlabel("Speed scale  (1x = real mouse max, 10x = 10x faster than observed)", fontsize=8)
ax_heat.set_ylabel("Hold time at peak (ms)", fontsize=8)
ax_heat.set_title(f"Worst-case detection error (mm)\n"
                  f"Green < {ERROR_THRESHOLD}mm PASS  |  Red > {ERROR_THRESHOLD}mm FAIL",
                  fontsize=9, fontweight="bold")

for ri in range(len(HEAT_HOLDS)):
    for ci in range(len(HEAT_SCALES)):
        val  = error_matrix[ri, ci]
        flag = "P" if val <= ERROR_THRESHOLD else "F"
        ax_heat.text(ci, ri, f"{val:.2f}\n{flag}", ha="center", va="center",
                     fontsize=6.5, color="black")

plt.colorbar(im, ax=ax_heat, shrink=0.8, label="Worst-case error (mm)")


# ── Video concentric vs step function ─────────────────────────────────────────
t_v, p_v = build_profile(1.0, 0, use_video_ascent=True)
t_s, p_s = build_profile(1.0, 0, use_video_ascent=False)

ax_conc.plot(t_v, p_v, color="#1565C0", linewidth=2, label="Video profile (1x)")
ax_conc.plot(t_s, p_s, color="#C62828", linewidth=1.5, linestyle="--",
             label=f"Step fn  ({V_MAX_MM_S:.0f}mm/s ramp)")

# Gravity descent annotation
t_grav_ref = np.linspace(0, 70, 300)
p_grav_ref = np.maximum(gravity_pos(t_grav_ref), 0)
t_grav_abs = T_LIFT_MS + t_grav_ref
ax_conc.plot(t_grav_abs, p_grav_ref, color="#2E7D32", linewidth=1.5,
             linestyle=":", label="Gravity freefall")

ax_conc.axhline(PEAK_MM - ERROR_THRESHOLD, color="gray", linewidth=0.8,
                linestyle="-.", label=f"Peak - {ERROR_THRESHOLD}mm")
ax_conc.set_xlabel("Time (ms)", fontsize=8)
ax_conc.set_ylabel("Position (mm)", fontsize=8)
ax_conc.set_title("Video concentric vs step function\nwith gravity descent",
                  fontsize=9, fontweight="bold")
ax_conc.legend(fontsize=6.5, framealpha=0.85)
ax_conc.set_ylim(-0.5, PEAK_MM + 1.5)


# ── Footer ─────────────────────────────────────────────────────────────────────
fig.text(
    0.5, 0.01,
    f"Gravity guarantee: {grav_drop_5ms:.3f}mm drop in first {DT_MS:.0f}ms after peak  |  "
    f"Threshold broken at >{t_drop_thresh:.0f}ms sampling  |  "
    f"Min hold time for +/-{ERROR_THRESHOLD}mm detection: 0 ms  |  "
    f"No sensor firmware smearing observed",
    ha="center", va="bottom", fontsize=8, family="monospace",
    bbox=dict(boxstyle="round,pad=0.4", facecolor="#EFEFEF", alpha=0.9)
)

plt.savefig("minimum_lift_detection_analysis.png", dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: minimum_lift_detection_analysis.png")
plt.show()
