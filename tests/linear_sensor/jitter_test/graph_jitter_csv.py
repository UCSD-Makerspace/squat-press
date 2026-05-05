"""
graph_jitter_csv.py — Jitter test sensor characterization
==========================================================
Usage:
    python graph_jitter_csv.py [path/to/jitter_sensor*.csv]

If no path is given, loads the most recent jitter_sensor*.csv in cwd.

What the data looks like (from jitter_test.ino):
  - UP strokes:   clear impulse response — rises to ~peak mm, decays back to rest
  - DOWN strokes: weight is already at floor — virtually no motion recorded
  - Burst end DOWN strokes span the 1-second inter-burst pause (no sync pulse
    during pause), so DOWN windows are 100ms coast + 1000ms pause = ~1100ms.
    This inflates DOWN row counts but the physics is just the floor characterisation.

Panels:
  1. Full session overview — every stroke as a coloured trace, stacked by stroke_no
  2. UP stroke overlay — all UP strokes time-aligned ± 1σ band (impulse response)
  3. Peak & trough tracking — per-stroke peak/settled values vs. stroke number + best fit
  4. UP peak distribution — histogram of detected peak positions (repeatability)
  5. Noise floor — coast-period σ for UP (settled oscillation) and DOWN (true floor)
"""

import sys
import glob
import os
import warnings
import csv as csvlib
from pathlib import Path

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from scipy import stats

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Timing windows (relative to the rising-edge sync pulse) ───────────────────
# Motor fires ~300us after rising edge, runs for ~5ms, then coasts.
# The weight reaches its peak around 15-20ms and has re-settled by ~50ms.
PEAK_SEARCH_END_S = 0.040   # look for peak/trough only within first 40ms
COAST_START_S     = 0.050   # weight has re-settled; use this window for noise

# ── Colours ───────────────────────────────────────────────────────────────────
UP_COLOR     = "#1565C0"   # dark blue
DOWN_COLOR   = "#C62828"   # dark red
SETTLE_COLOR = "#6A1B9A"   # purple
NOISE_COLOR  = "#2E7D32"   # green


# ── Data loading ───────────────────────────────────────────────────────────────

def load(path=None):
    if path is None:
        candidates = sorted(glob.glob("jitter_sensor*.csv"),
                            key=os.path.getmtime, reverse=True)
        if not candidates:
            sys.exit("No jitter_sensor*.csv in cwd. Pass the file path as argument.")
        path = candidates[0]
    print(f"Loading: {path}")

    rows = []
    with open(path, newline="") as f:
        for r in csvlib.DictReader(f):
            rows.append({
                "stroke_no":   int(r["stroke_no"]),
                "direction":   r["direction"].strip(),
                "time_s":      float(r["time_s"]),
                "position_mm": float(r["position_mm"]),
                "raw_value":   int(r["raw_value"]),
            })
    if not rows:
        sys.exit("CSV is empty.")
    return rows, Path(path).stem


# ── Group by stroke ────────────────────────────────────────────────────────────

def group_strokes(rows):
    strokes = {}
    for r in rows:
        sno = r["stroke_no"]
        strokes.setdefault(sno, []).append(r)
    for sno in strokes:
        strokes[sno].sort(key=lambda r: r["time_s"])
    return strokes


# ── Per-stroke statistics ──────────────────────────────────────────────────────

def compute_stats(strokes):
    records = []
    for sno in sorted(strokes):
        grp       = strokes[sno]
        direction = grp[0]["direction"]
        t         = np.array([r["time_s"]      for r in grp])
        pos       = np.array([r["position_mm"] for r in grp])

        # Baseline: median of readings in last 30% of window, or t < 0 if available
        coast_mask = t > COAST_START_S
        pre_mask   = t < 0.003

        if coast_mask.sum() >= 3:
            settled = np.median(pos[coast_mask])
        elif pre_mask.sum() >= 1:
            settled = np.median(pos[pre_mask])
        else:
            settled = pos[-1]

        # Peak/trough within the motion window only
        motion_mask = (t >= -0.005) & (t <= PEAK_SEARCH_END_S)
        pos_motion  = pos[motion_mask] if motion_mask.sum() >= 2 else pos

        peak_mm   = pos_motion.max()
        trough_mm = pos_motion.min()

        if direction == "UP":
            displacement = peak_mm - settled
            t_peak_idx   = np.argmax(pos_motion)
            t_peak        = t[motion_mask][t_peak_idx] if motion_mask.sum() else np.nan
        else:
            displacement = settled - trough_mm
            t_peak        = np.nan  # DOWN strokes don't have meaningful peaks

        # Noise floor: std dev during fully settled coast
        noise = pos[coast_mask].std() if coast_mask.sum() >= 5 else np.nan

        records.append(dict(
            stroke_no    = sno,
            direction    = direction,
            n_samples    = len(grp),
            settled_mm   = settled,
            peak_mm      = peak_mm,
            trough_mm    = trough_mm,
            displacement_mm = displacement,
            noise_mm     = noise,
            t_peak_s     = t_peak,
        ))
    return records


# ── Best-fit line ──────────────────────────────────────────────────────────────

def linfit(x, y):
    mask = np.isfinite(y)
    if mask.sum() < 3:
        return None
    sl, ic, r, _, _ = stats.linregress(x[mask].astype(float), y[mask])
    return sl, ic, r ** 2, sl * x + ic


# ── Reconstruct global time axis ───────────────────────────────────────────────

def global_time(strokes, stroke_stats):
    """
    Assign each stroke a global start time by summing actual window durations.
    Each stroke window = max(time_s) - min(time_s) of that stroke.
    """
    gt = {}
    cursor = 0.0
    for s in stroke_stats:
        sno = s["stroke_no"]
        grp = strokes[sno]
        t   = np.array([r["time_s"] for r in grp])
        gt[sno] = cursor - t.min()   # shift so that t=0 in the stroke aligns to cursor
        cursor  += t.max() - t.min() + 0.005   # 5ms gap between windows
    return gt


# ── Main plot ──────────────────────────────────────────────────────────────────

def plot(rows, strokes, stroke_stats, stem):
    up_stats   = [s for s in stroke_stats if s["direction"] == "UP"]
    down_stats = [s for s in stroke_stats if s["direction"] == "DOWN"]
    gt         = global_time(strokes, stroke_stats)

    fig = plt.figure(figsize=(20, 15))
    fig.patch.set_facecolor("#F8F8F8")
    fig.suptitle(
        f"Jitter Test — Linear Sensor Characterisation\n{stem}",
        fontsize=14, fontweight="bold", y=0.995
    )

    gs  = gridspec.GridSpec(3, 2, figure=fig,
                            hspace=0.52, wspace=0.35,
                            top=0.94, bottom=0.11, left=0.07, right=0.97)
    ax1 = fig.add_subplot(gs[0, :])   # full-width session overview
    ax2 = fig.add_subplot(gs[1, 0])   # UP overlay
    ax3 = fig.add_subplot(gs[1, 1])   # peak / settled tracking
    ax4 = fig.add_subplot(gs[2, 0])   # peak distribution
    ax5 = fig.add_subplot(gs[2, 1])   # noise floor

    for ax in (ax1, ax2, ax3, ax4, ax5):
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, alpha=0.22, linewidth=0.7)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

    # ── 1. Session overview ────────────────────────────────────────────────────
    # Plot every stroke as a trace on a continuous global time axis.
    # DOWN strokes capped at first 150ms to avoid the 1-second pause swamping the plot.
    global_series_t   = []
    global_series_pos = []
    global_series_dir = []

    for s in stroke_stats:
        sno = s["stroke_no"]
        grp = strokes[sno]
        direction = s["direction"]
        offset = gt[sno]
        for r in grp:
            adjusted_t = r["time_s"] + offset
            # Cap DOWN stroke display at 150ms past their start to keep the overview readable
            if direction == "DOWN" and r["time_s"] > 0.150:
                continue
            global_series_t.append(adjusted_t)
            global_series_pos.append(r["position_mm"])
            global_series_dir.append(direction)

    for direction, color in [("UP", UP_COLOR), ("DOWN", DOWN_COLOR)]:
        mask = [i for i, d in enumerate(global_series_dir) if d == direction]
        ax1.scatter(
            [global_series_t[i] for i in mask],
            [global_series_pos[i] for i in mask],
            s=4, alpha=0.5, color=color, linewidths=0, rasterized=True
        )

    # Peak markers for UP strokes
    for s in up_stats:
        if np.isfinite(s["t_peak_s"]):
            ax1.scatter(s["t_peak_s"] + gt[s["stroke_no"]], s["peak_mm"],
                        s=60, color="#0D47A1", marker="^", zorder=6, linewidths=0)

    ax1.set_xlabel("Reconstructed elapsed time (s)", fontsize=9)
    ax1.set_ylabel("Position (mm)", fontsize=9)
    ax1.set_title(
        f"Full Session Overview  —  {len(up_stats)} UP strokes, {len(down_stats)} DOWN strokes"
        f"  (DOWN display capped at 150ms to hide 1s inter-burst pause)",
        fontsize=9, fontweight="bold"
    )
    ax1.legend(handles=[
        Line2D([0],[0], color=UP_COLOR,   lw=0, marker="o", ms=5, label="UP"),
        Line2D([0],[0], color=DOWN_COLOR, lw=0, marker="o", ms=5, label="DOWN (first 150ms)"),
        Line2D([0],[0], color="#0D47A1",  lw=0, marker="^", ms=9, label="Detected peak"),
    ], fontsize=8, framealpha=0.85, loc="upper right")

    # ── 2. UP stroke overlay (impulse response) ───────────────────────────────
    common_t = np.linspace(-0.005, 0.100, 120)
    traces   = []

    for s in up_stats:
        grp = strokes[s["stroke_no"]]
        t   = np.array([r["time_s"]      for r in grp])
        pos = np.array([r["position_mm"] for r in grp])
        if len(t) < 4:
            continue
        interp = np.interp(common_t, t, pos,
                           left=pos[0], right=pos[-1])
        # Subtract each stroke's own settled baseline
        baseline = s["settled_mm"]
        traces.append(interp - baseline)

    if traces:
        arr  = np.array(traces)
        mean = arr.mean(axis=0)
        std  = arr.std(axis=0)

        for i, trace in enumerate(traces):
            ax2.plot(common_t * 1000, trace, color=UP_COLOR,
                     alpha=0.15, linewidth=0.8)
        ax2.plot(common_t * 1000, mean, color=UP_COLOR, linewidth=2.5,
                 label=f"Mean (n={len(traces)})")
        ax2.fill_between(common_t * 1000, mean - std, mean + std,
                         alpha=0.25, color=UP_COLOR, label="±1σ band")

    ax2.axvline(0,                  color="black",       linewidth=1.0, linestyle="--",
                label="Sync pulse (t=0)")
    ax2.axvline(COAST_START_S*1000, color=SETTLE_COLOR,  linewidth=1.0, linestyle=":",
                label=f"Coast start ({COAST_START_S*1000:.0f}ms)")
    ax2.axhline(0, color="gray", linewidth=0.5)
    ax2.set_xlim(common_t[0]*1000, common_t[-1]*1000)
    ax2.set_xlabel("Time within stroke (ms)", fontsize=9)
    ax2.set_ylabel("Position change from settled baseline (mm)", fontsize=9)
    ax2.set_title("UP Stroke Impulse Response\n(all strokes overlaid, baseline-subtracted)",
                  fontsize=10, fontweight="bold")
    ax2.legend(fontsize=7, framealpha=0.85)

    # ── 3. Peak & settled tracking with best fit ──────────────────────────────
    up_nos  = np.array([s["stroke_no"]  for s in up_stats])
    up_peak = np.array([s["peak_mm"]    for s in up_stats])
    up_settl= np.array([s["settled_mm"] for s in up_stats])

    ax3.scatter(up_nos, up_peak,  s=30, color=UP_COLOR,     alpha=0.8,
                label="UP peak",    marker="^", zorder=4)
    ax3.scatter(up_nos, up_settl, s=30, color=SETTLE_COLOR, alpha=0.8,
                label="UP settled", marker="s", zorder=4)

    for data, color, col_label in [
        (up_peak,   UP_COLOR,     "peak"),
        (up_settl,  SETTLE_COLOR, "settled"),
    ]:
        fit = linfit(up_nos, data)
        if fit:
            sl, ic, r2, y_fit = fit
            ax3.plot(up_nos, y_fit, color=color, linewidth=1.8, linestyle="--",
                     label=f"Fit ({col_label}): {sl*1e3:.2f} µm/stroke  R²={r2:.3f}")

    # DOWN strokes — show as near-zero floor
    if down_stats:
        dn_nos  = np.array([s["stroke_no"] for s in down_stats])
        dn_floor= np.array([s["settled_mm"] for s in down_stats])
        ax3.scatter(dn_nos, dn_floor, s=18, color=DOWN_COLOR, alpha=0.5,
                    marker="v", label="DOWN settled (floor)", zorder=3)

    ax3.set_xlabel("Stroke #", fontsize=9)
    ax3.set_ylabel("Position (mm)", fontsize=9)
    ax3.set_title("Peak & Settled Position per Stroke\nSlope = drift rate; scatter = repeatability",
                  fontsize=10, fontweight="bold")
    ax3.legend(fontsize=7, framealpha=0.85)

    # ── 4. UP peak distribution ───────────────────────────────────────────────
    valid_peaks = up_peak[np.isfinite(up_peak)]
    if len(valid_peaks):
        mean_peak = valid_peaks.mean()
        std_peak  = valid_peaks.std()
        cv        = (std_peak / mean_peak * 100) if mean_peak > 0 else float("nan")

        n_bins = min(20, max(5, len(valid_peaks)))
        ax4.hist(valid_peaks, bins=n_bins, color=UP_COLOR, alpha=0.7,
                 edgecolor="white", linewidth=0.5)
        ax4.axvline(mean_peak, color="black", linewidth=2, linestyle="--",
                    label=f"Mean: {mean_peak:.3f} mm")
        ax4.axvline(mean_peak + std_peak, color="#1565C0", linewidth=1,
                    linestyle=":", label=f"+1σ: {std_peak:.3f} mm  (CV={cv:.1f}%)")
        ax4.axvline(mean_peak - std_peak, color="#1565C0", linewidth=1, linestyle=":")

        # Expected from .ino constants (informational — may differ if settings were different)
        v_mm_s    = 2000 * 16 / (458.0 * 16)   # ~4.37 mm/s
        exp_disp  = v_mm_s * 0.005              # 5ms stroke
        ax4.axvline(exp_disp, color="gray", linewidth=1, linestyle="-.",
                    label=f"Expected (current .ino): {exp_disp:.3f} mm")

    ax4.set_xlabel("Detected peak position (mm)", fontsize=9)
    ax4.set_ylabel("Count", fontsize=9)
    ax4.set_title(f"UP Peak Distribution  (n={len(valid_peaks)} strokes)\nRepeatability / consistency",
                  fontsize=10, fontweight="bold")
    ax4.legend(fontsize=7, framealpha=0.85)

    # ── 5. Noise floor characterisation ───────────────────────────────────────
    up_noise   = np.array([s["noise_mm"] for s in up_stats   if np.isfinite(s.get("noise_mm", np.nan))])
    down_noise = np.array([s["noise_mm"] for s in down_stats if np.isfinite(s.get("noise_mm", np.nan))])

    all_noise = np.concatenate([up_noise, down_noise]) if len(up_noise) and len(down_noise) else (up_noise if len(up_noise) else down_noise)
    if len(all_noise):
        bin_edges = np.linspace(0, all_noise.max() * 1.1 + 1e-6, 20)
    else:
        bin_edges = 20

    if len(up_noise):
        ax5.hist(up_noise * 1000, bins=bin_edges * 1000, color=UP_COLOR, alpha=0.6,
                 edgecolor="white", linewidth=0.5, label=f"UP coast σ  (n={len(up_noise)})")
        ax5.axvline(up_noise.mean()*1000, color=UP_COLOR, linewidth=2, linestyle="--",
                    label=f"UP mean: {up_noise.mean()*1000:.2f} µm")

    if len(down_noise):
        ax5.hist(down_noise * 1000, bins=bin_edges * 1000, color=DOWN_COLOR, alpha=0.6,
                 edgecolor="white", linewidth=0.5, label=f"DOWN floor σ  (n={len(down_noise)})")
        ax5.axvline(down_noise.mean()*1000, color=DOWN_COLOR, linewidth=2, linestyle="--",
                    label=f"DOWN mean: {down_noise.mean()*1000:.2f} µm")

    if len(valid_peaks) and len(up_noise):
        signal_um = valid_peaks.mean() * 1000
        noise_um  = up_noise.mean() * 1000
        snr       = signal_um / noise_um if noise_um > 0 else float("nan")
        ax5.axvline(signal_um, color="black", linewidth=1.5, linestyle="-.",
                    label=f"UP signal ({signal_um:.0f} µm)  SNR={snr:.1f}")

    ax5.set_xlabel("Coast-period σ (µm)", fontsize=9)
    ax5.set_ylabel("Count", fontsize=9)
    ax5.set_title("Sensor Noise Floor\n(std dev during settled coast period)",
                  fontsize=10, fontweight="bold")
    ax5.legend(fontsize=7, framealpha=0.85)

    # ── Summary stats footer ───────────────────────────────────────────────────
    if len(valid_peaks) and len(up_noise):
        snr_str = f"{valid_peaks.mean()*1000 / (up_noise.mean()*1000):.1f}"
    else:
        snr_str = "N/A"

    cv_str = f"{valid_peaks.std()/valid_peaks.mean()*100:.1f}%" if len(valid_peaks) else "N/A"

    up_disp_arr  = np.array([s["displacement_mm"] for s in up_stats if np.isfinite(s["displacement_mm"])])

    lines = [
        (f"Strokes: {len(stroke_stats)} total  |  UP: {len(up_stats)}  |  DOWN: {len(down_stats)}  |  "
         f"Sensor rate: {len(rows)/max(1, sum(1 for s in up_stats)):.0f} samp/UP-stroke  (~219 Hz)"),

        (f"UP peak:  mean={valid_peaks.mean():.3f} mm  std={valid_peaks.std():.3f} mm  "
         f"CV={cv_str}  |  "
         f"UP displacement (peak−settled): mean={up_disp_arr.mean():.3f} mm  std={up_disp_arr.std():.3f} mm"),

        (f"Noise floor:  UP coast σ={up_noise.mean()*1000:.1f} µm  |  "
         f"DOWN floor σ={down_noise.mean()*1000:.1f} µm  |  SNR (UP signal/UP noise): {snr_str}"),
    ]
    fig.text(0.5, 0.005, "\n".join(lines), ha="center", va="bottom", fontsize=8,
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#EFEFEF",
                       alpha=0.95, linewidth=0.5))

    out = stem + "_analysis.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out}")
    plt.show()


# ── Terminal summary ───────────────────────────────────────────────────────────

def print_summary(stroke_stats):
    up   = [s for s in stroke_stats if s["direction"] == "UP"]
    down = [s for s in stroke_stats if s["direction"] == "DOWN"]

    peaks   = np.array([s["peak_mm"]    for s in up if np.isfinite(s["peak_mm"])])
    settles = np.array([s["settled_mm"] for s in up if np.isfinite(s["settled_mm"])])
    disps   = np.array([s["displacement_mm"] for s in up if np.isfinite(s["displacement_mm"])])
    noise_u = np.array([s["noise_mm"]   for s in up   if np.isfinite(s.get("noise_mm", np.nan))]) * 1000
    noise_d = np.array([s["noise_mm"]   for s in down if np.isfinite(s.get("noise_mm", np.nan))]) * 1000

    print("\n-- Stroke summary ---------------------------------------------------")
    print(f"  {'sno':>5}  {'dir':<5}  {'n_samp':>6}  {'peak_mm':>8}  {'settled':>8}  {'disp_mm':>8}  {'noise_um':>9}")
    for s in stroke_stats:
        print(f"  {s['stroke_no']:>5}  {s['direction']:<5}  {s['n_samples']:>6}  "
              f"{s['peak_mm']:>8.4f}  {s['settled_mm']:>8.4f}  "
              f"{s['displacement_mm']:>8.4f}  "
              f"{s['noise_mm']*1000 if np.isfinite(s.get('noise_mm', np.nan)) else float('nan'):>9.2f}")

    print(f"\n-- UP stroke aggregate ----------------------------------------------")
    if len(peaks):
        print(f"  Peak position      : {peaks.mean():.4f} +/- {peaks.std():.4f} mm  "
              f"(CV={peaks.std()/peaks.mean()*100:.1f}%,  range [{peaks.min():.4f}, {peaks.max():.4f}])")
    if len(settles):
        print(f"  Settled position   : {settles.mean():.4f} +/- {settles.std():.4f} mm")
    if len(disps):
        print(f"  Displacement       : {disps.mean():.4f} +/- {disps.std():.4f} mm")
    if len(noise_u):
        print(f"  Noise floor (coast): {noise_u.mean():.2f} +/- {noise_u.std():.2f} um")
    if len(noise_d):
        print(f"  DOWN floor (rest)  : {noise_d.mean():.2f} +/- {noise_d.std():.2f} um")
    if len(peaks) and len(noise_u):
        snr = peaks.mean() * 1000 / noise_u.mean()
        print(f"  SNR                : {snr:.1f}x")

    exp = 2000 * 16 / (458.0 * 16) * 0.005
    print(f"\n  Expected disp (current .ino, 5ms stroke): {exp:.4f} mm")
    if len(peaks):
        ratio = peaks.mean() / exp
        print(f"  Measured / expected ratio               : {ratio:.1f}x  "
              f"{'(test used different settings)' if ratio > 2 else ''}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    rows, stem = load(path)
    strokes     = group_strokes(rows)
    stroke_stats_list = compute_stats(strokes)

    if not stroke_stats_list:
        sys.exit("No strokes found.")

    print_summary(stroke_stats_list)
    plot(rows, strokes, stroke_stats_list, stem)


if __name__ == "__main__":
    main()
