import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load the data
filename = 'data_1_8_26_trial1.csv'
try:
    df = pd.read_csv(filename)
except FileNotFoundError:
    print(f"Error: {filename} not found. Please ensure the file is in the same directory.")
    exit()

# Basic validation of required columns
required_cols = {'time_s', 'position_mm', 'raw_value'}
missing = required_cols - set(df.columns)
if missing:
    print(f"Error: missing required columns: {missing}. Aborting.")
    exit()

print(f"Loaded {len(df)} data points.")

# --- CONFIGURATION ---
# Define thresholds to identify 'static' states
# We assume 'Bottom' is near 0.0 and 'Top' is near the max extension
BOTTOM_THRESHOLD_MM = 0.05
TOP_THRESHOLD_MM = 21.5 
VELOCITY_THRESHOLD = 0.1 # mm/s: samples with |velocity| <= this are considered static
# Smoothing and dwell parameters
VEL_SMOOTH_WINDOW = 5           # samples for rolling median of velocity (odd preferred)
MIN_DWELL_DURATION_S = 0.1      # minimum time (s) a run must be below velocity threshold to count as a dwell

# --- FILTER DATA ---
# Compute instantaneous velocity (mm/s) for every sample.
# Use np.gradient to get a full-length derivative (handles endpoints).
time = df['time_s'].to_numpy()
pos = df['position_mm'].to_numpy()
with np.errstate(divide='ignore', invalid='ignore'):
    velocity = np.gradient(pos, time)
df['velocity_mm_s'] = velocity

# Identify candidate dwell samples by position, then keep only those with low velocity
# Smooth the absolute velocity with a centered rolling median to avoid single-sample transients
vel_abs_sm = df['velocity_mm_s'].abs().rolling(window=VEL_SMOOTH_WINDOW, center=True, min_periods=1).median()

# Boolean mask of slow samples after smoothing
is_slow = vel_abs_sm <= VELOCITY_THRESHOLD

# Determine minimum sample count corresponding to MIN_DWELL_DURATION_S
median_dt = df['time_s'].diff().median()
if np.isnan(median_dt) or median_dt <= 0:
    min_samples = 1
else:
    min_samples = max(1, int(np.ceil(MIN_DWELL_DURATION_S / median_dt)))

# Find contiguous runs of `is_slow` and only keep runs long enough
accepted_slow = pd.Series(False, index=df.index)
if is_slow.any():
    # group id increments when is_slow changes
    grp = (is_slow != is_slow.shift(fill_value=False)).cumsum()
    for gid, idxs in df.groupby(grp).groups.items():
        # groups where is_slow at first index is True are candidate slow runs
        first_idx = idxs[0]
        if is_slow.loc[first_idx]:
            run_len = len(idxs)
            if run_len >= min_samples:
                accepted_slow.iloc[idxs] = True

# Identify candidate dwell samples by position, then keep only those inside accepted slow runs
bottom_candidates = df[df['position_mm'] <= BOTTOM_THRESHOLD_MM]
top_candidates = df[df['position_mm'] >= TOP_THRESHOLD_MM]

bottom_dwell = bottom_candidates[accepted_slow.loc[bottom_candidates.index]]
top_dwell = top_candidates[accepted_slow.loc[top_candidates.index]]

print(f"Bottom candidates: {len(bottom_candidates)} -> static after velocity filter & min-duration: {len(bottom_dwell)}")
print(f"Top candidates:    {len(top_candidates)} -> static after velocity filter & min-duration: {len(top_dwell)}")
print(f"median_dt={median_dt:.6f}s -> min_samples={min_samples}; VEL_SMOOTH_WINDOW={VEL_SMOOTH_WINDOW}")

# --- DIAGNOSTICS ---
print('\nVelocity statistics (mm/s):')
print(df['velocity_mm_s'].describe())

print('\nGlobal counts for velocity thresholds:')
for thr in [VELOCITY_THRESHOLD, 1e-6, 1e-5, 0.1]:
    print(f"  abs(vel) <= {thr}:", (df['velocity_mm_s'].abs() <= thr).sum())

print('\nCounts within position candidates:')
print('  bottom_candidates total:', len(bottom_candidates))
print('  bottom_candidates abs<=VELOCITY_THRESHOLD:', (bottom_candidates['velocity_mm_s'].abs() <= VELOCITY_THRESHOLD).sum())
print('  top_candidates total:', len(top_candidates))
print('  top_candidates abs<=VELOCITY_THRESHOLD:', (top_candidates['velocity_mm_s'].abs() <= VELOCITY_THRESHOLD).sum())

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
print_stats("TOP DWELL (~21.5mm)", top_dwell)

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
axes[0, 1].hist(bottom_dwell['raw_value'], bins=400, color='blue', alpha=0.7)
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
axes[1, 1].hist(top_dwell['raw_value'], bins=400, color='orange', alpha=0.7)
axes[1, 1].set_title('Distribution of Raw Values (Top)')
axes[1, 1].set_xlabel('Raw Sensor Value')
axes[1, 1].set_ylabel('Frequency')

plt.tight_layout()
plt.savefig('static_noise_analysis.png')
print("Saved figure to static_noise_analysis.png")
plt.show()