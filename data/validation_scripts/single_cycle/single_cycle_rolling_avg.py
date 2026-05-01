import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

CAMERA_FPS   = 240
TENSION_MM   = 22.0

# ── Paths ─────────────────────────────────────────────────────────────────────
truth_path  = '../../csv/2026.4.14/gt (1).csv'
sensor_path = '../../csv/2026.4.14/sensor2_no_gpio112145.csv'

# ── Load ──────────────────────────────────────────────────────────────────────
df_sensor = pd.read_csv(sensor_path)
df_truth  = pd.read_csv(truth_path)

# Handles both old format (time_s, position_mm, raw_value)
# and new format (cycle, time_s, position_mm, read_count, raw_rate_hz)
if 'cycle' in df_sensor.columns:
    df_sensor = df_sensor[df_sensor['cycle'] == 1].copy().reset_index(drop=True)

# Ground truth: frame -> seconds (frame 1 = t=0, LED-on frame)
df_truth['raw_time'] = (df_truth['frame'] - 1) / CAMERA_FPS

# ── Auto time-offset via cross-correlation sweep ──────────────────────────────
def find_time_offset(sensor_t, sensor_pos, truth_t, truth_pos,
                     search_range=0.2, resolution=0.001):
    offsets = np.arange(-search_range, search_range, resolution)
    errors  = []
    for offset in offsets:
        interp_pos = np.interp(truth_t, sensor_t + offset, sensor_pos,
                               left=np.nan, right=np.nan)
        mask = ~np.isnan(interp_pos)
        if mask.sum() < 5:
            errors.append(np.inf)
            continue
        rms = np.sqrt(np.mean((interp_pos[mask] - truth_pos[mask])**2))
        errors.append(rms)

    best_idx    = int(np.argmin(errors))
    best_offset = offsets[best_idx]
    best_rms    = errors[best_idx]
    return best_offset, best_rms, offsets, np.array(errors)

best_offset, best_rms, offsets, errors = find_time_offset(
    df_sensor['time_s'].values,
    df_sensor['position_mm'].values,
    df_truth['raw_time'].values,
    df_truth['mm'].values,
)

print(f"Auto-detected offset : {best_offset*1000:.1f} ms")
print(f"RMS at best offset   : {best_rms:.4f} mm")

df_sensor['sync_time'] = df_sensor['time_s'] + best_offset
df_truth['sync_time']  = df_truth['raw_time']

# ── Interpolate sensor onto truth timepoints ──────────────────────────────────
df_truth['sensor_val'] = np.interp(
    df_truth['sync_time'],
    df_sensor['sync_time'],
    df_sensor['position_mm'],
)
df_truth['error'] = df_truth['sensor_val'] - df_truth['mm']

# ── Metrics ───────────────────────────────────────────────────────────────────
def extract_metrics(time, pos):
    auc      = np.trapz(pos, time)
    peak     = np.max(pos)
    peak_t   = time[np.argmax(pos)]
    velocity = np.diff(pos) / np.diff(time)
    peak_vel = np.max(np.abs(velocity))
    return {'auc': auc, 'peak': peak, 'peak_t': peak_t, 'peak_vel': peak_vel}

sensor_metrics = extract_metrics(df_sensor['sync_time'].values, df_sensor['position_mm'].values)
truth_metrics  = extract_metrics(df_truth['sync_time'].values,  df_truth['mm'].values)

rms       = np.sqrt(np.mean(df_truth['error']**2))
peak_err  = df_truth['error'].abs().max()
peak_t_err = (sensor_metrics['peak_t'] - truth_metrics['peak_t']) * 1000

# TUT
tension_truth  = df_truth[df_truth['mm'] >= TENSION_MM]
tension_sensor = df_sensor[df_sensor['position_mm'] >= TENSION_MM]
tut_truth  = tension_truth['sync_time'].max()  - tension_truth['sync_time'].min()  if len(tension_truth)  > 1 else None
tut_sensor = tension_sensor['sync_time'].max() - tension_sensor['sync_time'].min() if len(tension_sensor) > 1 else None

print(f"AUC error          : {abs(sensor_metrics['auc'] - truth_metrics['auc']):.4f} mm·s")
print(f"Peak height error  : {abs(sensor_metrics['peak'] - truth_metrics['peak']):.4f} mm")
print(f"Peak timing error  : {peak_t_err:.1f} ms ({'sensor leads' if peak_t_err < 0 else 'sensor lags'})")
print(f"RMS position error : {rms:.4f} mm")
if tut_truth and tut_sensor:
    print(f"TUT truth          : {tut_truth*1000:.1f} ms")
    print(f"TUT sensor         : {tut_sensor*1000:.1f} ms")
    print(f"TUT error          : {abs(tut_truth - tut_sensor)*1000:.1f} ms")

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(13, 12))

# Panel 1: aligned comparison
ax1 = axes[0]
ax1.plot(df_sensor['sync_time'], df_sensor['position_mm'],
         label=f'Sensor (shifted {best_offset*1000:.1f}ms)', color='blue', alpha=0.7, lw=1.5)
ax1.scatter(df_truth['sync_time'], df_truth['mm'],
            color='red', label='Ground Truth', s=20, zorder=5)
ax1.axhline(TENSION_MM, color='green', linestyle='--', alpha=0.5, lw=1, label=f'{TENSION_MM}mm threshold')
ax1.set_title("Trigger-Synchronized Comparison (GPIO T=0)")
ax1.set_ylabel("Position (mm)")
ax1.set_xlabel("Time (s)")
ax1.legend(fontsize=9)
ax1.grid(True, alpha=0.25)

# Panel 2: error
ax2 = axes[1]
ax2.stem(df_truth['sync_time'], df_truth['error'], linefmt='purple', markerfmt='o', basefmt='k-')
ax2.fill_between(df_truth['sync_time'], df_truth['error'], 0, alpha=0.15, color='purple')
ax2.axhline(0, color='black', lw=0.8)
ax2.set_ylabel("Error: Sensor − Truth (mm)")
ax2.set_xlabel("Time since GPIO Trigger (s)")
ax2.set_title(f"Position Error  |  RMS={rms:.3f}mm  Peak={peak_err:.3f}mm")
ax2.grid(True, alpha=0.25)

# Panel 3: offset search curve
ax3 = axes[2]
ax3.plot(np.array(offsets) * 1000, errors, color='teal', lw=1.5)
ax3.axvline(best_offset * 1000, color='red', linestyle='--',
            label=f'Best offset: {best_offset*1000:.1f}ms')
ax3.set_xlabel("Time offset (ms)")
ax3.set_ylabel("RMS error (mm)")
ax3.set_title("Cross-correlation offset search")
ax3.legend()
ax3.grid(True, alpha=0.25)

plt.tight_layout()
plt.savefig("validation_plot.png", dpi=150, bbox_inches='tight')
plt.show()
print("Plot saved to validation_plot.png")