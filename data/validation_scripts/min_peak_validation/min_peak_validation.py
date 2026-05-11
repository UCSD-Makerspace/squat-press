"""
Minimum peak validation for mice squat-press sensor logs.
=========================================================

This script answers the question:

    Can the sensor reliably record the peak of a realistic mouse lift
    within a +/- 0.5 mm tolerance?

It reads the logger CSV formats used in this repository, groups rows into
individual lift cycles, extracts the detected peak for each cycle, and marks a
cycle as valid when the detected peak is at least 19.0 mm.

Supported CSV schemas:
  - cycle,time_s,position_mm,raw_value
  - stroke_no,direction,time_ms,time_s,position_mm,raw_value

Outputs:
  - console summary
  - per-cycle CSV summary
  - JSON session summary
  - saved PNG figures with cycle traces and distributions
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from scipy import stats


GROUND_TRUTH_PEAK_MM = 19.5
VALID_MIN_PEAK_MM = 19.0
MIN_SAMPLES_PER_CYCLE = 5
MIN_CYCLE_DURATION_S = 0.060
TIME_RESET_DROP_S = 0.020

PASS_COLOR = "#2E7D32"
FAIL_COLOR = "#C62828"
UNDER_COLOR = "#EF6C00"
NEUTRAL_COLOR = "#1565C0"
ACCENT_COLOR = "#6A1B9A"
BG_COLOR = "#F8F8F8"
GRID_COLOR = "#DADADA"


@dataclass
class CycleSummary:
    cycle_id: str
    cycle_index: int
    direction: str | None
    n_samples: int
    start_s: float
    end_s: float
    duration_s: float
    peak_time_s: float
    peak_mm: float
    raw_value_at_peak: int | None
    mean_dt_s: float
    std_dt_s: float
    valid: bool
    undersampled: bool
    signed_error_mm: float
    abs_error_mm: float
    miss_mm: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate minimum detectable peak height for squat-lift sensor CSV logs."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="CSV file(s) or directory paths. If omitted, uses the newest CSV in data/csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for figures and summaries. Defaults to a sibling folder next to each CSV.",
    )
    parser.add_argument(
        "--ground-truth-mm",
        type=float,
        default=GROUND_TRUTH_PEAK_MM,
        help="Programmed peak displacement to compare against (default: 19.5).",
    )
    parser.add_argument(
        "--valid-min-mm",
        type=float,
        default=VALID_MIN_PEAK_MM,
        help="Minimum detected peak required to count as a valid lift event (default: 19.0).",
    )
    parser.add_argument(
        "--direction-filter",
        default="UP",
        help="Direction to keep when a direction column exists. Use ALL to keep every row.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Also open the figures after saving them.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def is_csv_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".csv"


def newest_csv_path() -> Path:
    roots = [repo_root() / "data" / "csv", Path.cwd()]
    candidates: list[Path] = []
    for root in roots:
        if root.exists():
            candidates.extend(sorted(root.rglob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True))
    if not candidates:
        raise FileNotFoundError("No CSV files found under data/csv or the current directory.")
    return candidates[0]


def resolve_input_paths(raw_inputs: list[str]) -> list[Path]:
    if not raw_inputs:
        return [newest_csv_path()]

    paths: list[Path] = []
    for item in raw_inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.csv")))
        elif is_csv_file(path):
            paths.append(path)
        else:
            raise FileNotFoundError(f"Input path does not exist or is not a CSV: {path}")

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            unique_paths.append(path)
            seen.add(resolved)
    if not unique_paths:
        raise FileNotFoundError("No CSV files were found for the provided input path(s).")
    return unique_paths


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_rows(path: Path, direction_filter: str = "UP") -> tuple[list[dict], list[str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        rows: list[dict] = []

        has_direction = "direction" in fieldnames
        keep_direction = direction_filter.strip().upper() != "ALL"
        direction_target = direction_filter.strip().upper()

        for order, raw_row in enumerate(reader):
            if not raw_row:
                continue

            row = {key.strip(): value for key, value in raw_row.items() if key is not None}
            position_mm = _safe_float(row.get("position_mm"))
            if position_mm is None:
                continue

            if row.get("time_s") is not None and _safe_float(row.get("time_s")) is not None:
                time_s = float(row.get("time_s"))
            elif row.get("time_ms") is not None and _safe_float(row.get("time_ms")) is not None:
                time_s = float(row.get("time_ms")) / 1000.0
            else:
                raise ValueError(f"CSV {path} does not contain a usable time_s or time_ms column.")

            direction = None
            if has_direction:
                direction = str(row.get("direction", "")).strip().upper() or None
                if keep_direction and direction != direction_target:
                    continue

            cycle_id = row.get("cycle") or row.get("stroke_no")
            cycle_label = str(cycle_id).strip() if cycle_id is not None and str(cycle_id).strip() else None

            rows.append(
                {
                    "order": order,
                    "cycle_id": cycle_label,
                    "direction": direction,
                    "time_s": time_s,
                    "position_mm": position_mm,
                    "raw_value": _safe_int(row.get("raw_value")),
                }
            )

    if has_direction and direction_filter.strip().upper() != "ALL" and not rows:
        raise ValueError(
            f"No rows matched direction filter {direction_filter!r} in {path.name}. Use --direction-filter ALL if needed."
        )
    if not rows:
        raise ValueError(f"CSV {path} did not yield any usable data rows.")
    return rows, fieldnames


def _sort_cycle_key(value: str | None) -> tuple[int, object]:
    if value is None:
        return (1, "")
    try:
        return (0, int(value))
    except ValueError:
        return (0, value)


def group_cycles(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    if any(row["cycle_id"] is not None for row in rows):
        buckets: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            if row["cycle_id"] is None:
                continue
            buckets[row["cycle_id"]].append(row)

        grouped: list[tuple[str, list[dict]]] = []
        for cycle_id in sorted(buckets.keys(), key=_sort_cycle_key):
            ordered = sorted(buckets[cycle_id], key=lambda item: (item["time_s"], item["order"]))
            grouped.append((cycle_id, ordered))
        return grouped

    ordered_rows = sorted(rows, key=lambda item: item["order"])
    groups: list[list[dict]] = []
    current_group: list[dict] = [ordered_rows[0]]
    previous_time = ordered_rows[0]["time_s"]

    for row in ordered_rows[1:]:
        time_s = row["time_s"]
        if time_s < previous_time - TIME_RESET_DROP_S:
            groups.append(current_group)
            current_group = [row]
        else:
            current_group.append(row)
        previous_time = time_s

    groups.append(current_group)
    return [(str(index + 1), group) for index, group in enumerate(groups)]


def summarize_cycle(cycle_id: str, cycle_index: int, rows: list[dict]) -> CycleSummary:
    ordered = sorted(rows, key=lambda item: (item["time_s"], item["order"]))
    times = np.asarray([float(item["time_s"]) for item in ordered], dtype=float)
    positions = np.asarray([float(item["position_mm"]) for item in ordered], dtype=float)

    peak_index = int(np.argmax(positions))
    peak_mm = float(positions[peak_index])
    peak_time_s = float(times[peak_index])
    raw_value_at_peak = ordered[peak_index]["raw_value"]
    start_s = float(times[0])
    end_s = float(times[-1])
    duration_s = float(max(end_s - start_s, 0.0))

    if len(times) > 1:
        dts = np.diff(times)
        mean_dt_s = float(np.mean(dts))
        std_dt_s = float(np.std(dts, ddof=1)) if len(dts) > 1 else 0.0
    else:
        mean_dt_s = float("nan")
        std_dt_s = float("nan")

    valid = peak_mm >= VALID_MIN_PEAK_MM
    undersampled = (
        len(ordered) < MIN_SAMPLES_PER_CYCLE
        or duration_s < MIN_CYCLE_DURATION_S
        or peak_index == 0
        or peak_index == len(ordered) - 1
    )

    signed_error_mm = peak_mm - GROUND_TRUTH_PEAK_MM
    abs_error_mm = abs(signed_error_mm)
    miss_mm = max(0.0, VALID_MIN_PEAK_MM - peak_mm)

    return CycleSummary(
        cycle_id=str(cycle_id),
        cycle_index=cycle_index,
        direction=ordered[0].get("direction"),
        n_samples=len(ordered),
        start_s=start_s,
        end_s=end_s,
        duration_s=duration_s,
        peak_time_s=peak_time_s,
        peak_mm=peak_mm,
        raw_value_at_peak=raw_value_at_peak,
        mean_dt_s=mean_dt_s,
        std_dt_s=std_dt_s,
        valid=valid,
        undersampled=undersampled,
        signed_error_mm=signed_error_mm,
        abs_error_mm=abs_error_mm,
        miss_mm=miss_mm,
    )


def compute_session_summary(cycles: list[CycleSummary], ground_truth_mm: float, valid_min_mm: float) -> dict:
    peaks = np.asarray([cycle.peak_mm for cycle in cycles], dtype=float)
    peak_times = np.asarray([cycle.peak_time_s for cycle in cycles], dtype=float)
    durations = np.asarray([cycle.duration_s for cycle in cycles], dtype=float)
    sample_counts = np.asarray([cycle.n_samples for cycle in cycles], dtype=float)
    errors = peaks - ground_truth_mm
    cycle_numbers = np.asarray([cycle.cycle_index for cycle in cycles], dtype=float)

    valid_mask = peaks >= valid_min_mm
    undersampled_mask = np.asarray([cycle.undersampled for cycle in cycles], dtype=bool)

    duration_mean = float(np.mean(durations))
    duration_std = float(np.std(durations, ddof=1)) if len(durations) > 1 else 0.0
    peak_time_mean = float(np.mean(peak_times))
    peak_time_std = float(np.std(peak_times, ddof=1)) if len(peak_times) > 1 else 0.0

    dt_values = np.asarray([cycle.mean_dt_s for cycle in cycles if np.isfinite(cycle.mean_dt_s)], dtype=float)
    dt_mean = float(np.mean(dt_values)) if len(dt_values) else float("nan")
    dt_std = float(np.std(dt_values, ddof=1)) if len(dt_values) > 1 else float("nan")

    if len(cycles) > 1:
        peak_trend = stats.linregress(cycle_numbers, peaks)
        peak_time_trend = stats.linregress(cycle_numbers, peak_times)
        duration_trend = stats.linregress(cycle_numbers, durations)
    else:
        peak_trend = peak_time_trend = duration_trend = None

    return {
        "cycle_count": int(len(cycles)),
        "valid_count": int(valid_mask.sum()),
        "failure_count": int((~valid_mask).sum()),
        "failure_rate": float((~valid_mask).sum() / len(cycles)) if cycles else float("nan"),
        "undersampled_count": int(undersampled_mask.sum()),
        "peak_mean_mm": float(np.mean(peaks)),
        "peak_std_mm": float(np.std(peaks, ddof=1)) if len(peaks) > 1 else 0.0,
        "peak_min_mm": float(np.min(peaks)),
        "peak_max_mm": float(np.max(peaks)),
        "error_mean_mm": float(np.mean(errors)),
        "error_std_mm": float(np.std(errors, ddof=1)) if len(errors) > 1 else 0.0,
        "error_mae_mm": float(np.mean(np.abs(errors))),
        "error_rmse_mm": float(np.sqrt(np.mean(errors ** 2))),
        "duration_mean_s": duration_mean,
        "duration_std_s": duration_std,
        "duration_cv": float(duration_std / duration_mean) if duration_mean else float("nan"),
        "peak_time_mean_s": float(peak_time_mean),
        "peak_time_std_s": float(peak_time_std),
        "peak_time_cv": float(peak_time_std / peak_time_mean) if peak_time_mean else float("nan"),
        "sample_mean": float(np.mean(sample_counts)),
        "sample_std": float(np.std(sample_counts, ddof=1)) if len(sample_counts) > 1 else 0.0,
        "dt_mean_s": dt_mean,
        "dt_std_s": dt_std,
        "peak_trend": peak_trend,
        "peak_time_trend": peak_time_trend,
        "duration_trend": duration_trend,
        "ground_truth_mm": ground_truth_mm,
        "valid_min_mm": valid_min_mm,
    }


def print_console_summary(source_path: Path, cycles: list[CycleSummary], summary: dict) -> None:
    print()
    print("=" * 80)
    print(f"MINIMUM PEAK VALIDATION  |  {source_path.name}")
    print("=" * 80)
    print(
        f"Cycles: {summary['cycle_count']}  |  Valid: {summary['valid_count']}  |  "
        f"Failures: {summary['failure_count']}  ({summary['failure_rate'] * 100:.1f}%)  |  "
        f"Undersampled: {summary['undersampled_count']}"
    )
    print(
        f"Detected peak: {summary['peak_mean_mm']:.3f} ± {summary['peak_std_mm']:.3f} mm  |  "
        f"Error vs {summary['ground_truth_mm']:.1f} mm: {summary['error_mean_mm']:+.3f} ± {summary['error_std_mm']:.3f} mm"
    )
    print(
        f"MAE: {summary['error_mae_mm']:.3f} mm  |  RMSE: {summary['error_rmse_mm']:.3f} mm  |  "
        f"Cycle duration: {summary['duration_mean_s']:.3f} ± {summary['duration_std_s']:.3f} s"
    )
    print(
        f"Peak timing: {summary['peak_time_mean_s']:.3f} ± {summary['peak_time_std_s']:.3f} s  |  "
        f"Mean sample interval: {summary['dt_mean_s']:.3f} s"
    )

    if summary["peak_trend"] is not None:
        peak_trend = summary["peak_trend"]
        peak_time_trend = summary["peak_time_trend"]
        duration_trend = summary["duration_trend"]
        print(
            f"Peak trend: {peak_trend.slope:+.4f} mm/cycle  (R²={peak_trend.rvalue ** 2:.3f})"
        )
        print(
            f"Peak timing trend: {peak_time_trend.slope:+.4f} s/cycle  (R²={peak_time_trend.rvalue ** 2:.3f})"
        )
        print(
            f"Duration trend: {duration_trend.slope:+.4f} s/cycle  (R²={duration_trend.rvalue ** 2:.3f})"
        )

    print()
    print("Per-cycle results")
    print(
        f"{'cycle':>8}  {'samples':>7}  {'peak(mm)':>8}  {'error(mm)':>9}  {'valid':>5}  "
        f"{'undersamp':>9}  {'duration(s)':>11}  {'peak_t(s)':>9}"
    )
    print("-" * 80)
    for cycle in cycles:
        print(
            f"{cycle.cycle_id:>8}  {cycle.n_samples:>7}  {cycle.peak_mm:>8.3f}  {cycle.signed_error_mm:>+9.3f}  "
            f"{str(cycle.valid):>5}  {str(cycle.undersampled):>9}  {cycle.duration_s:>11.3f}  {cycle.peak_time_s:>9.3f}"
        )


def write_cycle_csv(output_dir: Path, source_path: Path, cycles: list[CycleSummary]) -> Path:
    out_path = output_dir / f"{source_path.stem}_cycle_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(cycles[0]).keys()))
        writer.writeheader()
        for cycle in cycles:
            writer.writerow(asdict(cycle))
    return out_path


def write_summary_json(output_dir: Path, source_path: Path, summary: dict, cycles: list[CycleSummary]) -> Path:
    out_path = output_dir / f"{source_path.stem}_summary.json"
    serializable = {}
    for key, value in summary.items():
        if key.endswith("trend") and value is not None:
            serializable[key] = {
                "slope": float(value.slope),
                "intercept": float(value.intercept),
                "rvalue": float(value.rvalue),
                "pvalue": float(value.pvalue),
                "stderr": float(value.stderr),
            }
        else:
            serializable[key] = value
    serializable["source_file"] = str(source_path)
    serializable["cycles"] = [asdict(cycle) for cycle in cycles]
    with out_path.open("w") as handle:
        json.dump(serializable, handle, indent=2)
    return out_path


def build_plots(
    output_dir: Path,
    source_path: Path,
    cycles: list[CycleSummary],
    grouped_rows: list[tuple[str, list[dict]]],
    summary: dict,
    show: bool = False,
) -> Path:
    trace_lookup = {cycle_id: rows for cycle_id, rows in grouped_rows}

    cycle_numbers = np.asarray([cycle.cycle_index for cycle in cycles], dtype=float)
    peaks = np.asarray([cycle.peak_mm for cycle in cycles], dtype=float)
    errors = peaks - summary["ground_truth_mm"]
    durations = np.asarray([cycle.duration_s for cycle in cycles], dtype=float)
    peak_times = np.asarray([cycle.peak_time_s for cycle in cycles], dtype=float)
    sample_counts = np.asarray([cycle.n_samples for cycle in cycles], dtype=float)

    fig = plt.figure(figsize=(20, 15), constrained_layout=False)
    fig.patch.set_facecolor(BG_COLOR)
    fig.suptitle(
        f"Minimum Peak Validation — {source_path.stem}\n"
        f"Target {summary['ground_truth_mm']:.1f} mm  |  Valid if >= {summary['valid_min_mm']:.1f} mm",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )
    gs = gridspec.GridSpec(
        3,
        2,
        figure=fig,
        height_ratios=[2.1, 1.1, 1.1],
        hspace=0.45,
        wspace=0.28,
        top=0.92,
        bottom=0.08,
        left=0.06,
        right=0.97,
    )

    ax_trace = fig.add_subplot(gs[0, :])
    ax_peak = fig.add_subplot(gs[1, 0])
    ax_error = fig.add_subplot(gs[1, 1])
    ax_timing = fig.add_subplot(gs[2, 0])
    ax_samples = fig.add_subplot(gs[2, 1])

    for ax in (ax_trace, ax_peak, ax_error, ax_timing, ax_samples):
        ax.set_facecolor("white")
        ax.grid(True, alpha=0.22, linewidth=0.7, color=GRID_COLOR)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

    for cycle in cycles:
        rows = trace_lookup.get(cycle.cycle_id, [])
        if not rows:
            continue
        times = np.asarray([float(item["time_s"]) for item in rows], dtype=float)
        positions = np.asarray([float(item["position_mm"]) for item in rows], dtype=float)
        peak_index = int(np.argmax(positions))

        color = PASS_COLOR if cycle.valid else FAIL_COLOR
        linestyle = "--" if cycle.undersampled else "-"
        if cycle.undersampled and cycle.valid:
            color = UNDER_COLOR

        ax_trace.plot(times * 1000.0, positions, color=color, linewidth=1.5, alpha=0.85, linestyle=linestyle)
        ax_trace.scatter(
            times[peak_index] * 1000.0,
            positions[peak_index],
            s=28,
            color=color,
            marker="^" if cycle.valid else "x",
            zorder=5,
        )

    ax_trace.axhspan(summary["valid_min_mm"], summary["ground_truth_mm"] + (summary["ground_truth_mm"] - summary["valid_min_mm"]), color=PASS_COLOR, alpha=0.08)
    ax_trace.axhline(summary["valid_min_mm"], color=FAIL_COLOR, linestyle="--", linewidth=1.0, label=f"Valid threshold {summary['valid_min_mm']:.1f} mm")
    ax_trace.axhline(summary["ground_truth_mm"], color=NEUTRAL_COLOR, linestyle=":", linewidth=1.2, label=f"Ground truth {summary['ground_truth_mm']:.1f} mm")
    ax_trace.set_xlim(-5, max(float(np.max([cycle.end_s for cycle in cycles])) * 1000.0, 50.0))
    ax_trace.set_ylim(0, max(float(np.max(peaks)) + 1.0, summary["ground_truth_mm"] + 1.0))
    ax_trace.set_xlabel("Time within cycle (ms)")
    ax_trace.set_ylabel("Position (mm)")
    ax_trace.set_title(
        f"Cycle traces  |  green = valid, red = failure, orange = undersampled  |  n={summary['cycle_count']}",
        fontsize=10,
        fontweight="bold",
    )
    ax_trace.legend(
        handles=[
            Line2D([0], [0], color=PASS_COLOR, lw=2, label="Valid cycle"),
            Line2D([0], [0], color=FAIL_COLOR, lw=2, label="Failed cycle"),
            Line2D([0], [0], color=UNDER_COLOR, lw=2, linestyle="--", label="Undersampled cycle"),
            Line2D([0], [0], color=NEUTRAL_COLOR, lw=1.2, linestyle=":", label="Ground truth"),
        ],
        fontsize=8,
        framealpha=0.9,
        loc="upper right",
    )

    n_bins_peak = min(20, max(5, len(peaks)))
    ax_peak.hist(peaks, bins=n_bins_peak, color=NEUTRAL_COLOR, alpha=0.72, edgecolor="white", linewidth=0.6)
    ax_peak.axvline(np.mean(peaks), color="black", linewidth=2.0, linestyle="--", label=f"Mean {np.mean(peaks):.3f} mm")
    ax_peak.axvline(summary["valid_min_mm"], color=FAIL_COLOR, linewidth=1.2, linestyle="--", label=f"Valid threshold {summary['valid_min_mm']:.1f} mm")
    ax_peak.axvline(summary["ground_truth_mm"], color=NEUTRAL_COLOR, linewidth=1.2, linestyle=":", label=f"Ground truth {summary['ground_truth_mm']:.1f} mm")
    ax_peak.set_xlabel("Detected peak position (mm)")
    ax_peak.set_ylabel("Count")
    ax_peak.set_title("Detected peak distribution", fontsize=10, fontweight="bold")
    ax_peak.legend(fontsize=7, framealpha=0.9)

    error_bins = min(20, max(5, len(errors)))
    ax_error.hist(errors, bins=error_bins, color=ACCENT_COLOR, alpha=0.72, edgecolor="white", linewidth=0.6)
    ax_error.axvspan(-0.5, 0.5, color=PASS_COLOR, alpha=0.12, label="±0.5 mm tolerance")
    ax_error.axvline(0.0, color="black", linewidth=2.0, linestyle="--", label="Zero error")
    ax_error.set_xlabel("Detected peak - ground truth (mm)")
    ax_error.set_ylabel("Count")
    ax_error.set_title("Peak error histogram", fontsize=10, fontweight="bold")
    ax_error.legend(fontsize=7, framealpha=0.9)

    ax_timing.scatter(cycle_numbers, peak_times * 1000.0, s=28, color=NEUTRAL_COLOR, alpha=0.85, label="Peak time")
    if summary["peak_time_trend"] is not None:
        fit = summary["peak_time_trend"]
        ax_timing.plot(cycle_numbers, (fit.slope * cycle_numbers + fit.intercept) * 1000.0, color=NEUTRAL_COLOR, linestyle="--", linewidth=1.5)
    ax_timing.set_xlabel("Cycle #")
    ax_timing.set_ylabel("Peak time from cycle start (ms)", color=NEUTRAL_COLOR)
    ax_timing.tick_params(axis="y", labelcolor=NEUTRAL_COLOR)
    ax_timing.set_title("Temporal consistency", fontsize=10, fontweight="bold")

    ax_timing2 = ax_timing.twinx()
    ax_timing2.scatter(cycle_numbers, durations * 1000.0, s=24, color=ACCENT_COLOR, alpha=0.75, marker="s", label="Cycle duration")
    if summary["duration_trend"] is not None:
        fit = summary["duration_trend"]
        ax_timing2.plot(cycle_numbers, (fit.slope * cycle_numbers + fit.intercept) * 1000.0, color=ACCENT_COLOR, linestyle=":", linewidth=1.5)
    ax_timing2.set_ylabel("Cycle duration (ms)", color=ACCENT_COLOR)
    ax_timing2.tick_params(axis="y", labelcolor=ACCENT_COLOR)

    trend_text = []
    if summary["peak_time_trend"] is not None:
        trend_text.append(f"peak slope {summary['peak_time_trend'].slope * 1000.0:+.2f} ms/cycle")
    if summary["duration_trend"] is not None:
        trend_text.append(f"duration slope {summary['duration_trend'].slope * 1000.0:+.2f} ms/cycle")
    if trend_text:
        ax_timing.text(
            0.02,
            0.97,
            "\n".join(trend_text),
            transform=ax_timing.transAxes,
            va="top",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.88, edgecolor="#CCCCCC"),
        )

    bins_samples = max(4, min(12, len(sample_counts)))
    ax_samples.hist(sample_counts, bins=bins_samples, color=UNDER_COLOR, alpha=0.65, edgecolor="white", linewidth=0.6)
    ax_samples.axvline(MIN_SAMPLES_PER_CYCLE, color=FAIL_COLOR, linestyle="--", linewidth=1.4, label=f"Undersample threshold {MIN_SAMPLES_PER_CYCLE} samples")
    ax_samples.axvline(np.mean(sample_counts), color="black", linestyle=":", linewidth=1.4, label=f"Mean {np.mean(sample_counts):.1f} samples")
    ax_samples.set_xlabel("Samples per cycle")
    ax_samples.set_ylabel("Count")
    ax_samples.set_title("Sampling density", fontsize=10, fontweight="bold")
    ax_samples.legend(fontsize=7, framealpha=0.9)

    footer = (
        f"Failure rate: {summary['failure_rate'] * 100:.1f}%  |  "
        f"Peak mean: {summary['peak_mean_mm']:.3f} mm  |  "
        f"Error RMSE: {summary['error_rmse_mm']:.3f} mm  |  "
        f"Duration CV: {summary['duration_cv'] * 100:.2f}%"
    )
    fig.text(
        0.5,
        0.01,
        footer,
        ha="center",
        va="bottom",
        fontsize=8,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#EFEFEF", alpha=0.95),
    )

    out_path = output_dir / f"{source_path.stem}_peak_validation_overview.png"
    fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    if show:
        plt.show()
    plt.close(fig)
    return out_path


def process_csv(path: Path, args: argparse.Namespace) -> None:
    rows, _fieldnames = load_rows(path, direction_filter=args.direction_filter)
    grouped_rows = group_cycles(rows)
    cycles = [summarize_cycle(cycle_id, index + 1, cycle_rows) for index, (cycle_id, cycle_rows) in enumerate(grouped_rows)]

    if not cycles:
        raise ValueError(f"No complete cycles were found in {path}")

    summary = compute_session_summary(cycles, args.ground_truth_mm, args.valid_min_mm)
    print_console_summary(path, cycles, summary)

    output_dir = args.output_dir if args.output_dir else path.parent / f"{path.stem}_min_peak_validation"
    output_dir.mkdir(parents=True, exist_ok=True)

    cycle_csv = write_cycle_csv(output_dir, path, cycles)
    summary_json = write_summary_json(output_dir, path, summary, cycles)
    figure_path = build_plots(output_dir, path, cycles, grouped_rows, summary, show=args.show)

    print()
    print(f"Saved cycle summary: {cycle_csv}")
    print(f"Saved JSON summary:   {summary_json}")
    print(f"Saved figure:         {figure_path}")
    print(f"Saved figures in:     {output_dir}")


def main() -> None:
    args = parse_args()
    if args.output_dir is not None:
        args.output_dir = Path(args.output_dir)

    input_paths = resolve_input_paths(args.inputs)
    for path in input_paths:
        process_csv(path, args)


if __name__ == "__main__":
    main()
