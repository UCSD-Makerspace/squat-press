import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. Load Data
truth_path = '../../csv/2026.03.31/gt (1).csv'
sensor_path = '../../csv/2026.03.31/sensor2_134943.csv'

# 32ms accounts for the processing delay between the sensor and ground truth.
# Without this, the error "flies off" the axis during fast movements.
TIME_SHIFT = 0.032 

df_s = pd.read_csv(sensor_path)
df_t = pd.read_csv(truth_path)

# 2. Synchronize & Interpolate
df_s['calibrated_time'] = df_s['time_s'] + TIME_SHIFT
df_t['sync_time'] = (df_t['frame'] - 1) / 240.0

# Map Ground Truth points to the Sensor's calibrated timeline
t_interp = np.interp(df_s['calibrated_time'], df_t['sync_time'], df_t['mm'])
peak_idx = df_s['position_mm'].idxmax()

# 3. Calculate Error (mm)
error_mm = df_s['position_mm'] - t_interp

# 4. Visualization
plt.figure(figsize=(12, 6))

# Concentric vs Eccentric Phase split
plt.plot(df_s['calibrated_time'][:peak_idx], error_mm[:peak_idx], 
         color='darkblue', label='Concentric Phase (Upward)', lw=2)
plt.plot(df_s['calibrated_time'][peak_idx:], error_mm[peak_idx:], 
         color='orange', label='Eccentric Phase (Downward)', lw=2)

# Aesthetic and functional formatting
plt.axhline(0, color='black', lw=1.2, alpha=0.8)
plt.fill_between(df_s['calibrated_time'], error_mm, color='gray', alpha=0.1)

# Fixed Y-limits to contain the data and show stability
plt.ylim(-1.5, 1.5) 

plt.title("Absolute Displacement Error (Post-Calibration)", fontsize=14)
plt.xlabel("Time (s)", fontsize=12)
plt.ylabel("Error (mm)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.3)
plt.legend(loc='upper right')

plt.tight_layout()
plt.show()

# Final accuracy metrics for your report
print(f"Peak Error Magnitude: {np.max(np.abs(error_mm)):.3f} mm")
print(f"Mean Absolute Error: {np.mean(np.abs(error_mm)):.3f} mm")