import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

TIME_OFFSET = -0.007

# 1. Load Data
truth_path  = '../../csv/2026.03.31/gt (1).csv'
sensor_path = '../../csv/2026.03.31/sensor2_134943.csv'

df_sensor = pd.read_csv(sensor_path)
df_truth = pd.read_csv(truth_path)

# 2. Synchronize to GPIO Trigger (T=0)
# Sensor time is already relative to GPIO HIGH in your RPi script
df_sensor['sync_time'] = df_sensor['time_s'] + TIME_OFFSET

# Ground truth time relative to the frame the LED turns ON (assume Frame 1)
df_truth['sync_time'] = (df_truth['frame'] - 1) / 240.0

# 3. Direct Comparison via Interpolation
df_truth['sensor_val'] = np.interp(
    df_truth['sync_time'], 
    df_sensor['sync_time'], 
    df_sensor['position_mm']
)

df_truth['error'] = df_truth['sensor_val'] - df_truth['mm']

# 4. Visualization
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

ax1.plot(df_sensor['sync_time'], df_sensor['position_mm'], label='Sensor Data', color='blue', alpha=0.4)
ax1.scatter(df_truth['sync_time'], df_truth['mm'], color='red', label='Ground Truth', s=20)
ax1.set_title("Trigger-Synchronized Comparison (GPIO T=0)")
ax1.set_ylabel("Position (mm)")
ax1.legend()

ax2.stem(df_truth['sync_time'], df_truth['error'], linefmt='purple', markerfmt='o')
ax2.set_ylabel("Error (mm)")
ax2.set_xlabel("Time since GPIO Trigger (s)")

# Function to extract functional metrics
def extract_metrics(time, pos):
    auc = np.trapz(pos, time)
    peak = np.max(pos)
    # Velocity (central difference)
    velocity = np.diff(pos) / np.diff(time)
    peak_vel = np.max(velocity)
    return {'auc': auc, 'peak': peak, 'peak_vel': peak_vel}

sensor_metrics = extract_metrics(df_sensor['time_s'], df_sensor['position_mm'])
truth_metrics = extract_metrics(df_truth['sync_time'], df_truth['mm'])

print(f"AUC Error: {abs(sensor_metrics['auc'] - truth_metrics['auc']):.4f}")
print(f"Peak Height Error: {abs(sensor_metrics['peak'] - truth_metrics['peak']):.4f} mm")

plt.tight_layout()
plt.show()