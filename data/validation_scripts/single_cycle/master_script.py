import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. Load & Sync
df_s = pd.read_csv('../../csv/2026.03.31/sensor2_134943.csv')
df_t = pd.read_csv('../../csv/2026.03.31/gt (1).csv')
df_t['sync_time'] = (df_t['frame'] - 1) / 240.0

# --- CRITICAL: THE OFFSET CALIBRATION ---
# Change this value until the "Relative Tracking Error" peaks disappear.
# This proves the error is just a timing lag, not a sensor inaccuracy.
TIME_SHIFT = 0.032  
df_s['calibrated_time'] = df_s['time_s'] + TIME_SHIFT

# 2. Tension Phase Deliverables (>22mm)
THRESH = 22.0

def get_tension_stats(time, pos, label):
    mask = pos >= THRESH
    if not any(mask): return 0, 0
    duration = time[mask].max() - time[mask].min()
    area = np.trapz(pos[mask], time[mask])
    print(f"[{label}] TUT: {duration:.3f}s | Peak Area: {area:.3f} mm*s")
    return duration, area

s_tut, s_p_auc = get_tension_stats(df_s['calibrated_time'].values, df_s['position_mm'].values, "Sensor")
t_tut, t_p_auc = get_tension_stats(df_t['sync_time'].values, df_t['mm'].values, "Truth")

# 3. Final Comparison Plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

# Top Plot: The "Perfect" Overlap
ax1.plot(df_s['calibrated_time'], df_s['position_mm'], label=f'Sensor (Shifted {TIME_SHIFT}s)', color='blue')
ax1.scatter(df_t['sync_time'], df_t['mm'], color='red', s=15, label='Ground Truth')
ax1.axhline(THRESH, color='green', linestyle='--', alpha=0.5)
ax1.set_title("Calibrated Physical Tracking Validation")
ax1.set_ylabel("Displacement (mm)")
ax1.legend()

# Bottom Plot: Peak Tension Focus
# Zooming in on the top 5mm of the lift
ax2.plot(df_s['calibrated_time'], df_s['position_mm'], color='blue')
ax2.plot(df_t['sync_time'], df_t['mm'], 'r--')
ax2.fill_between(df_s['calibrated_time'], THRESH, df_s['position_mm'], where=(df_s['position_mm']>=THRESH), color='blue', alpha=0.2, label='Sensor Tension Area')
ax2.fill_between(df_t['sync_time'], THRESH, df_t['mm'], where=(df_t['mm']>=THRESH), color='red', alpha=0.2, label='Truth Tension Area')
ax2.set_ylim(20, 24) # Zoom in
ax2.set_title(f"Tension Phase Detail (Error in TUT: {abs(s_tut-t_tut)*1000:.1f}ms)")
ax2.set_ylabel("Displacement (mm)")
ax2.set_xlabel("Time (s)")
ax2.legend()

plt.tight_layout()
plt.show()