import pandas as pd
import matplotlib.pyplot as plt

# Load the data
filename = 'data.csv'
try:
    df = pd.read_csv(filename)
except FileNotFoundError:
    print(f"Error: {filename} not found. Please ensure the file is in the same directory.")
    exit()

print(f"Loaded {len(df)} data points.")

# --- CONFIGURATION ---
# Define thresholds to identify 'static' states
# We assume 'Bottom' is near 0.0 and 'Top' is near the max extension
BOTTOM_THRESHOLD_MM = 0.1
TOP_THRESHOLD_MM = 20.0 

# --- FILTER DATA ---
# Filter data where the sensor is sitting at the bottom
bottom_dwell = df[df['position_mm'] <= BOTTOM_THRESHOLD_MM]

# Filter data where the sensor is holding at the top
top_dwell = df[df['position_mm'] >= TOP_THRESHOLD_MM]

# --- CALCULATE STATISTICS ---
def print_stats(name, data_slice):
    if len(data_slice) == 0:
        print(f"\n--- {name} (No Data Found) ---")
        return

    print(f"\n--- {name} Statistics ---")
    print(f"Count:      {len(data_slice)} samples")
    print(f"Duration:   {data_slice['time_s'].iloc[-1] - data_slice['time_s'].iloc[0]:.2f} seconds (approx total span)")
    
    # Position Stats
    pos_mean = data_slice['position_mm'].mean()
    pos_std = data_slice['position_mm'].std()
    pos_peak_to_peak = data_slice['position_mm'].max() - data_slice['position_mm'].min()
    
    print(f"Position:   Mean={pos_mean:.4f} mm | StdDev={pos_std:.4f} mm | Pk-Pk={pos_peak_to_peak:.4f} mm")

    # Raw Value Stats (The actual sensor bits)
    raw_mean = data_slice['raw_value'].mean()
    raw_std = data_slice['raw_value'].std()
    raw_peak_to_peak = data_slice['raw_value'].max() - data_slice['raw_value'].min()
    
    print(f"Raw Value:  Mean={raw_mean:.2f}    | StdDev={raw_std:.2f}    | Pk-Pk={raw_peak_to_peak:.2f}")

print_stats("BOTTOM DWELL (0mm)", bottom_dwell)
print_stats("TOP DWELL (~22mm)", top_dwell)

# --- PLOTTING ---
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
fig.suptitle(f'Static Noise Analysis: {filename}', fontsize=16)

# 1. Time Series of Raw Value at Bottom
axes[0, 0].plot(bottom_dwell['time_s'], bottom_dwell['raw_value'], '.', markersize=2, alpha=0.5, color='blue')
axes[0, 0].set_title('Noise at Bottom (Raw Value)')
axes[0, 0].set_ylabel('Raw Sensor Value')
axes[0, 0].set_xlabel('Time (s)')
axes[0, 0].grid(True, alpha=0.3)

# 2. Histogram of Raw Value at Bottom
axes[0, 1].hist(bottom_dwell['raw_value'], bins=30, color='blue', alpha=0.7)
axes[0, 1].set_title('Distribution of Raw Values (Bottom)')
axes[0, 1].set_xlabel('Raw Sensor Value')
axes[0, 1].set_ylabel('Frequency')

# 3. Time Series of Raw Value at Top
axes[1, 0].plot(top_dwell['time_s'], top_dwell['raw_value'], '.', markersize=2, alpha=0.5, color='orange')
axes[1, 0].set_title('Noise at Top (Raw Value)')
axes[1, 0].set_ylabel('Raw Sensor Value')
axes[1, 0].set_xlabel('Time (s)')
axes[1, 0].grid(True, alpha=0.3)

# 4. Histogram of Raw Value at Top
axes[1, 1].hist(top_dwell['raw_value'], bins=30, color='orange', alpha=0.7)
axes[1, 1].set_title('Distribution of Raw Values (Top)')
axes[1, 1].set_xlabel('Raw Sensor Value')
axes[1, 1].set_ylabel('Frequency')

plt.tight_layout()
plt.show()