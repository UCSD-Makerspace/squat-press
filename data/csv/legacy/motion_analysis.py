import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

filename = 'csv/LXK_40hz_2026.01.20.csv'
try:
    df = pd.read_csv(filename)
except FileNotFoundError:
    print(f"Error: {filename} not found.")
    exit()

# --- SEGMENTATION LOGIC (Identifying Potential Cycles) ---
THRESHOLD_MM = 0.5
MIN_PEAK_POSITION_MM = 15.0  # Filter: A good cycle should reach at least 15 mm
MIN_CYCLE_DURATION_S = 0.5   # Filter: A good cycle should last at least 0.5 seconds

df['active'] = df['position_mm'] > THRESHOLD_MM
df['transition'] = df['active'].astype(int).diff()

starts_raw = df.index[df['transition'] == 1].tolist()
ends_raw = df.index[df['transition'] == -1].tolist()

# Handle edge cases
if len(ends_raw) < len(starts_raw):
    ends_raw.append(len(df) - 1)
if len(starts_raw) > len(ends_raw):
    starts_raw = starts_raw[:len(ends_raw)]

print(f"Detected {len(starts_raw)} raw potential motion cycles.")

# --- FILTERING LOGIC ---
starts_filtered = []
ends_filtered = []
discarded_count = 0

for start_idx, end_idx in zip(starts_raw, ends_raw):
    segment = df.loc[start_idx:end_idx].copy()

    # 1. Check Peak Position
    peak_position = segment['position_mm'].max()
    
    # 2. Check Cycle Duration (using time from start to end of active region)
    if not segment.empty:
        start_time = df.loc[start_idx, 'time_s']
        end_time = df.loc[end_idx, 'time_s']
        cycle_duration = end_time - start_time
    else:
        # Should not happen with proper start/end indices, but for safety
        cycle_duration = 0
        
    if peak_position >= MIN_PEAK_POSITION_MM and cycle_duration >= MIN_CYCLE_DURATION_S:
        starts_filtered.append(start_idx)
        ends_filtered.append(end_idx)
    else:
        discarded_count += 1

cycles = len(starts_filtered)
print(f"Filtered to {cycles} valid motion cycles (Discarded: {discarded_count}).")

# --- PLOTTING SETUP ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
fig.suptitle(f'Motion Dynamics Overlay ({cycles} filtered cycles)', fontsize=16)

colors = plt.cm.viridis(np.linspace(0, 1, cycles))

for i, (start_idx, end_idx) in enumerate(zip(starts_filtered, ends_filtered)):
    # Add padding to see the lift-off and return-to-home
    pad = 5
    s = max(0, start_idx - pad)
    e = min(len(df), end_idx + pad)
    
    segment = df.iloc[s:e].copy()
    
    # Normalize Time: Set t=0 to the start of the movement
    start_time = df.loc[start_idx, 'time_s']
    segment['norm_time'] = segment['time_s'] - start_time
    
    # Calculate Velocity (mm/s)
    segment['velocity'] = segment['position_mm'].diff() / segment['time_s'].diff()
    
    # Apply a slight smoothing to velocity
    segment['velocity_smooth'] = segment['velocity'].rolling(window=3).mean()

    # Plot Position
    ax1.plot(segment['norm_time'], segment['position_mm'], label=f'Cycle {i+1}', color=colors[i], linewidth=1.5, alpha=0.8)

    # Plot Velocity
    ax2.plot(segment['norm_time'], segment['velocity_smooth'], label=f'Cycle {i+1}', color=colors[i], linewidth=1.5, alpha=0.8)

# Formatting Position Plot
ax1.set_title('Position vs Normalized Time (Repeatability Check) - Filtered')
ax1.set_xlabel('Time since movement start (s)')
ax1.set_ylabel('Position (mm)')
ax1.grid(True, which='both', linestyle='--', alpha=0.5)
# Hide legend if there are many cycles
if cycles < 30:
    ax1.legend(loc='upper right', fontsize='small')

# Formatting Velocity Plot
ax2.set_title('Velocity Profile (Smoothness Check) - Filtered')
ax2.set_xlabel('Time since movement start (s)')
ax2.set_ylabel('Velocity (mm/s)')
ax2.grid(True, which='both', linestyle='--', alpha=0.5)
# Add a zero line for velocity
ax2.axhline(0, color='black', linewidth=1, alpha=0.5)

plt.tight_layout()
plt.show()
print("Saved filtered motion dynamics plot to motion_dynamics_overlay_filtered.png")