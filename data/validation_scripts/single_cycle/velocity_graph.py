import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

# 1. Load Data
truth_path = '../../csv/2026.04.09/gt (1).csv'
sensor_path = '../../csv/2026.04.09/sensor2_142307.csv'
TIME_SHIFT = -0.009  # 32ms hardware/processing latency

df_s = pd.read_csv(sensor_path)
df_t = pd.read_csv(truth_path)

# 2. Synchronize
df_s['calibrated_time'] = df_s['time_s'] + TIME_SHIFT
df_t['sync_time'] = (df_t['frame'] - 1) / 240.0

# 3. Interpolate and Calculate Velocity
# Map Truth to Sensor's high-freq clock
t_interp = np.interp(df_s['calibrated_time'], df_t['sync_time'], df_t['mm'])

# Derivative (v = ds/dt)
v_s_raw = np.gradient(df_s['position_mm'], df_s['calibrated_time'])
v_t_raw = np.gradient(t_interp, df_s['calibrated_time'])

# Smooth to remove sampling noise (Window=11, Poly=3)
v_s_smooth = savgol_filter(v_s_raw, 11, 3)
v_t_smooth = savgol_filter(v_t_raw, 11, 3)

# 4. Plot
plt.figure(figsize=(12, 6))
plt.plot(df_s['calibrated_time'], v_s_smooth, label='Sensor Velocity (mm/s)', color='blue', lw=2)
plt.plot(df_s['calibrated_time'], v_t_smooth, 'r--', label='Smoothed Ground Truth', alpha=0.8)

plt.title("Velocity Profile: Concentric vs. Eccentric Validation", fontsize=14)
plt.xlabel("Time since GPIO Trigger (s)", fontsize=12)
plt.ylabel("Velocity (mm/s)", fontsize=12)
plt.axhline(0, color='black', lw=1)
plt.grid(True, alpha=0.3)
plt.legend()
plt.show()