"""
graph_jitter_overlay.py — UP stroke shape overlay + pulse timing
=================================================================
Usage:
    python graph_jitter_overlay.py [path/to/jitter_sensor*.csv]

Produces two figures:

Figure 1 — Shape overlay
  Left:  Raw traces coloured blue->red by stroke order.
  Right: Peak-normalised traces — isolates shape from amplitude.

Figure 2 — Pulse timing
  Left:  Velocity profiles (d(pos)/dt) overlaid.
         Motor-on phase shows as a roughly flat positive-velocity plateau
         for ~5ms, then decays as inertia carries the weight and gravity
         returns it.  Directly answers "how long is the actual lift?".
  Right: Per-stroke timing metrics vs stroke number:
         - t_peak (ms): time from sync pulse to position peak
         - FWHM  (ms): full-width at half-maximum of position pulse
         Both should be roughly constant if the motor timing is consistent.
"""

import sys
import glob
import os
import csv as csvlib
from pathlib import Path

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colorbar import ColorbarBase
from matplotlib.colors import Normalize
from scipy import stats
from scipy.ndimage import uniform_filter1d


# ── Load ──────────────────────────────────────────────────────────────────────

def load(path=None):
    if path is None:
        candidates = sorted(glob.glob("jitter_sensor*.csv"),
                            key=os.path.getmtime, reverse=True)
        if not candidates:
            sys.exit("No jitter_sensor*.csv in cwd. Pass path as argument.")
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
            })
    if not rows:
        sys.exit("CSV is empty.")
    return rows, Path(path).stem


# ── Build interpolated traces ──────────────────────────────────────────────────

COMMON_T = np.linspace(-0.005, 0.100, 200)   # 200 points, -5ms to 100ms


def build_traces(rows, direction="UP"):
    strokes = {}
    for r in rows:
        if r["direction"] == direction:
            strokes.setdefault(r["stroke_no"], []).append(r)

    stroke_nos = sorted(strokes)
    traces     = []

    for sno in stroke_nos:
        grp = sorted(strokes[sno], key=lambda r: r["time_s"])
        t   = np.array([r["time_s"]      for r in grp])
        pos = np.array([r["position_mm"] for r in grp])
        if len(t) < 4:
            continue
        interp = np.interp(COMMON_T, t, pos, left=pos[0], right=pos[-1])
        # Subtract per-stroke baseline: median of coast period (t > 50ms)
        coast = interp[COMMON_T > 0.050]
        baseline = np.median(coast) if len(coast) >= 3 else interp[-1]
        interp -= baseline
        traces.append((sno, interp))

    return traces   # list of (stroke_no, trace_array)


# ── Main plot ──────────────────────────────────────────────────────────────────

def plot(up_traces, stem):
    if not up_traces:
        sys.exit("No UP strokes found.")

    stroke_nos = np.array([sno for sno, _ in up_traces])
    arrays     = np.array([tr  for _, tr  in up_traces])

    n          = len(up_traces)
    cmap       = cm.get_cmap("coolwarm", n)
    norm       = Normalize(vmin=stroke_nos.min(), vmax=stroke_nos.max())
    t_ms       = COMMON_T * 1000

    mean_raw   = arrays.mean(axis=0)
    std_raw    = arrays.std(axis=0)

    # Peak-normalised: divide each trace by its own peak
    peak_vals  = arrays.max(axis=1, keepdims=True)
    peak_vals  = np.where(peak_vals > 0.01, peak_vals, 1.0)   # avoid div-by-zero on flat traces
    arrays_norm = arrays / peak_vals
    mean_norm  = arrays_norm.mean(axis=0)
    std_norm   = arrays_norm.std(axis=0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(17, 7))
    fig.patch.set_facecolor("#F8F8F8")
    fig.suptitle(
        f"UP Stroke Overlay — Shape & Amplitude Analysis\n{stem}",
        fontsize=13, fontweight="bold", y=1.00
    )

    for ax in (ax1, ax2):
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, alpha=0.20, linewidth=0.7)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

    # ── Left: Raw traces ───────────────────────────────────────────────────────
    for i, (sno, trace) in enumerate(up_traces):
        color = cmap(norm(sno))
        ax1.plot(t_ms, trace, color=color, alpha=0.55, linewidth=0.9)

    ax1.plot(t_ms, mean_raw, color="black", linewidth=2.5, zorder=10, label="Mean")
    ax1.fill_between(t_ms, mean_raw - std_raw, mean_raw + std_raw,
                     alpha=0.18, color="black", label="+/-1s band")

    ax1.axvline(0,    color="#555", linewidth=1.0, linestyle="--", label="Sync pulse (t=0)")
    ax1.axvline(5,    color="#888", linewidth=0.8, linestyle=":",  label="Motor stop (~5ms)")
    ax1.axhline(0,    color="#aaa", linewidth=0.5)
    ax1.set_xlim(t_ms[0], t_ms[-1])
    ax1.set_xlabel("Time within stroke (ms)", fontsize=10)
    ax1.set_ylabel("Position (mm, baseline-subtracted)", fontsize=10)
    ax1.set_title(f"Raw amplitude  —  {n} UP strokes\n"
                  f"Colour: blue = early strokes, red = late strokes",
                  fontsize=10, fontweight="bold")
    ax1.legend(fontsize=8, framealpha=0.85, loc="upper right")

    # ── Right: Peak-normalised traces ─────────────────────────────────────────
    for i, (sno, _) in enumerate(up_traces):
        color = cmap(norm(sno))
        ax2.plot(t_ms, arrays_norm[i], color=color, alpha=0.55, linewidth=0.9)

    ax2.plot(t_ms, mean_norm, color="black", linewidth=2.5, zorder=10, label="Mean")
    ax2.fill_between(t_ms, mean_norm - std_norm, mean_norm + std_norm,
                     alpha=0.18, color="black", label="+/-1s band")

    ax2.axvline(0, color="#555", linewidth=1.0, linestyle="--", label="Sync pulse (t=0)")
    ax2.axvline(5, color="#888", linewidth=0.8, linestyle=":",  label="Motor stop (~5ms)")
    ax2.axhline(0, color="#aaa", linewidth=0.5)
    ax2.set_xlim(t_ms[0], t_ms[-1])
    ax2.set_xlabel("Time within stroke (ms)", fontsize=10)
    ax2.set_ylabel("Normalised position (0 = baseline, 1 = peak)", fontsize=10)
    ax2.set_title(f"Peak-normalised shape  —  {n} UP strokes\n"
                  f"Consistent shape = amplitude-only change; diverging = profile change",
                  fontsize=10, fontweight="bold")
    ax2.legend(fontsize=8, framealpha=0.85, loc="upper right")

    # ── Shared colourbar ──────────────────────────────────────────────────────
    fig.subplots_adjust(bottom=0.14, top=0.90, left=0.07, right=0.93, wspace=0.30)
    cbar_ax = fig.add_axes([0.25, 0.04, 0.50, 0.025])
    cb = ColorbarBase(cbar_ax, cmap=cmap, norm=norm, orientation="horizontal")
    cb.set_label("Stroke number  (earlier → later)", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    out = stem + "_overlay.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out}")
    plt.show()


# ── Per-stroke timing metrics ──────────────────────────────────────────────────

def stroke_timing(up_traces):
    """
    For each UP stroke compute:
      t_peak_ms  — time from sync pulse (t=0) to position peak
      fwhm_ms    — full-width at half-maximum of the position pulse
    Returns list of dicts, one per stroke.
    """
    dt = COMMON_T[1] - COMMON_T[0]   # seconds per interpolated sample
    records = []

    for sno, trace in up_traces:
        peak_val = trace.max()
        if peak_val < 0.01:           # flat trace — skip
            continue

        peak_idx  = trace.argmax()
        t_peak_ms = COMMON_T[peak_idx] * 1000

        # FWHM: find crossings of half-peak on rising and falling sides
        half = peak_val / 2.0
        rising_idx  = np.where((trace[:peak_idx] < half))[0]
        falling_idx = np.where((trace[peak_idx:] < half))[0]

        if len(rising_idx) and len(falling_idx):
            t_rise = COMMON_T[rising_idx[-1]] * 1000    # last sample below half before peak
            t_fall = COMMON_T[peak_idx + falling_idx[0]] * 1000  # first sample below half after peak
            fwhm_ms = t_fall - t_rise
        else:
            fwhm_ms = np.nan

        records.append(dict(stroke_no=sno, t_peak_ms=t_peak_ms, fwhm_ms=fwhm_ms,
                            peak_mm=peak_val))
    return records


# ── Pulse timing figure ────────────────────────────────────────────────────────

def plot_timing(up_traces, stem):
    if not up_traces:
        return

    stroke_nos = np.array([sno for sno, _ in up_traces])
    arrays     = np.array([tr  for _, tr  in up_traces])

    n    = len(up_traces)
    cmap = cm.get_cmap("coolwarm", n)
    norm = Normalize(vmin=stroke_nos.min(), vmax=stroke_nos.max())
    t_ms = COMMON_T * 1000
    dt_s = COMMON_T[1] - COMMON_T[0]

    # Velocity: smooth each trace first (5-sample box = ~2.5ms), then differentiate
    SMOOTH = 5
    vel_arrays = np.gradient(
        uniform_filter1d(arrays, size=SMOOTH, axis=1),
        dt_s, axis=1
    )   # mm/s

    mean_vel = vel_arrays.mean(axis=0)
    std_vel  = vel_arrays.std(axis=0)

    timing = stroke_timing(up_traces)
    t_peaks = np.array([r["t_peak_ms"] for r in timing])
    fwhms   = np.array([r["fwhm_ms"]   for r in timing])
    tnos    = np.array([r["stroke_no"] for r in timing], dtype=float)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(17, 7))
    fig.patch.set_facecolor("#F8F8F8")
    fig.suptitle(
        f"UP Stroke Pulse Timing\n{stem}",
        fontsize=13, fontweight="bold", y=1.00
    )

    for ax in (ax1, ax2):
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, alpha=0.20, linewidth=0.7)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

    # ── Left: Velocity profiles ───────────────────────────────────────────────
    for i, (sno, _) in enumerate(up_traces):
        ax1.plot(t_ms, vel_arrays[i], color=cmap(norm(sno)), alpha=0.40, linewidth=0.8)

    ax1.plot(t_ms, mean_vel, color="black", linewidth=2.5, zorder=10, label="Mean velocity")
    ax1.fill_between(t_ms, mean_vel - std_vel, mean_vel + std_vel,
                     alpha=0.15, color="black", label="+/-1s band")

    ax1.axvline(0, color="#555", linewidth=1.0, linestyle="--", label="Sync pulse (t=0)")
    ax1.axvline(5, color="#E53935", linewidth=1.2, linestyle=":",
                label="Expected motor stop (~5ms)")
    ax1.axhline(0, color="#aaa", linewidth=0.6)

    # Annotate the motor-on plateau region
    plateau_mask = (t_ms >= 0) & (t_ms <= 5)
    if plateau_mask.any():
        v_plateau = mean_vel[plateau_mask].mean()
        ax1.annotate(
            f"Motor-on plateau\n~{v_plateau:.0f} mm/s",
            xy=(2.5, v_plateau),
            xytext=(15, v_plateau * 0.6),
            fontsize=8,
            arrowprops=dict(arrowstyle="->", color="#333", lw=0.8),
            color="#333"
        )

    ax1.set_xlim(t_ms[0], t_ms[-1])
    ax1.set_xlabel("Time within stroke (ms)", fontsize=10)
    ax1.set_ylabel("Velocity (mm/s)", fontsize=10)
    ax1.set_title(
        "Velocity profiles (d pos / dt)\n"
        "Flat positive plateau = motor driving; zero crossing = peak; negative = return",
        fontsize=10, fontweight="bold"
    )
    ax1.legend(fontsize=8, framealpha=0.85, loc="upper right")

    # ── Right: Timing metrics per stroke ──────────────────────────────────────
    ax2.scatter(tnos, t_peaks, color="#1565C0", s=40, zorder=4, label="t_peak (ms)")
    ax2.scatter(tnos, fwhms,   color="#E53935", s=40, marker="s", zorder=4, label="FWHM (ms)")

    # Best-fit lines
    for data, color, label in [
        (t_peaks, "#1565C0", "t_peak fit"),
        (fwhms,   "#E53935", "FWHM fit"),
    ]:
        mask = np.isfinite(data)
        if mask.sum() >= 3:
            sl, ic, r2, _, _ = stats.linregress(tnos[mask], data[mask])
            y_fit = sl * tnos + ic
            ax2.plot(tnos, y_fit, color=color, linewidth=1.6, linestyle="--",
                     label=f"{label}: slope={sl:.2f} ms/stroke  R2={r2:.3f}")

    # Reference lines for the .ino expected values
    ax2.axhline(5, color="gray", linewidth=1.0, linestyle="-.",
                label="Expected motor-on: 5 ms")

    mean_tp = np.nanmean(t_peaks)
    mean_fw = np.nanmean(fwhms)
    ax2.set_xlabel("Stroke #", fontsize=10)
    ax2.set_ylabel("Time (ms)", fontsize=10)
    ax2.set_title(
        f"t_peak: {mean_tp:.1f} ms mean  |  FWHM: {mean_fw:.1f} ms mean\n"
        f"Flat trend = consistent timing; slope = drift in impulse duration",
        fontsize=10, fontweight="bold"
    )
    ax2.legend(fontsize=7, framealpha=0.85)

    # ── Colourbar (velocity panel only) ───────────────────────────────────────
    fig.subplots_adjust(bottom=0.14, top=0.90, left=0.07, right=0.93, wspace=0.32)
    cbar_ax = fig.add_axes([0.07, 0.04, 0.40, 0.025])
    cb = ColorbarBase(cbar_ax, cmap=cmap, norm=norm, orientation="horizontal")
    cb.set_label("Stroke number  (earlier -> later)", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    out = stem + "_timing.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out}")
    plt.show()

    # Print timing summary
    print("\n-- Pulse timing per UP stroke -----------------------------------")
    print(f"  {'sno':>5}  {'t_peak_ms':>10}  {'fwhm_ms':>9}  {'peak_mm':>9}")
    for r in timing:
        print(f"  {r['stroke_no']:>5}  {r['t_peak_ms']:>10.2f}  "
              f"{r['fwhm_ms']:>9.2f}  {r['peak_mm']:>9.4f}")
    print(f"\n  t_peak:  mean={np.nanmean(t_peaks):.2f} ms  "
          f"std={np.nanstd(t_peaks):.2f} ms")
    print(f"  FWHM:    mean={np.nanmean(fwhms):.2f} ms  "
          f"std={np.nanstd(fwhms):.2f} ms")
    print(f"  Expected motor-on duration: 5 ms")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    rows, stem = load(path)
    up_traces  = build_traces(rows, "UP")
    plot(up_traces, stem)
    plot_timing(up_traces, stem)


if __name__ == "__main__":
    main()
