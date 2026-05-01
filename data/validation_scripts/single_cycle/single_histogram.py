import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load Data
df_sensor = pd.read_csv('../../csv/2026.04.09/sensor2_142307.csv')
df_truth = pd.read_csv('../../csv/2026.04.09/gt (1).csv')

# Syncing: Using the hardware trigger (GPIO T=0)
df_truth['sync_time'] = (df_truth['frame'] - 1) / 240.0
sensor_interp = np.interp(df_truth['sync_time'], df_sensor['time_s'], df_sensor['position_mm'])

# Error in Microns (Sensor - Truth)
errors = (sensor_interp - df_truth['mm']) * 1000

plt.figure(figsize=(8, 5))
plt.hist(errors, bins=25, color='skyblue', edgecolor='black', alpha=0.7)
plt.axvline(0, color='red', linestyle='dashed', label='Perfect Accuracy')
plt.title("Sensor Reliability Histogram")
plt.xlabel("Measurement Error (Microns)")
plt.ylabel("Frequency (Count)")
plt.legend()
plt.show()

print(f"Mean Error: {np.mean(errors):.2f} um")
print(f"Standard Deviation: {np.std(errors):.2f} um")