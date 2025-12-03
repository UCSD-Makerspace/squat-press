import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

filename = 'data.csv'
try:
    df = pd.read_csv(filename)
except FileNotFoundError:
    print(f"Error: {filename} not found.")
    exit()

# --- SEGMENTATION LOGIC ---
# We want to identify individual "strokes".
# A stroke starts when we leave 0.5mm and ends when we return to 0.5mm.
THRESHOLD_MM = 0.5

# Create a mask for when we are "In Motion" (above threshold)
df['active'] = df['position_mm'] > THRESHOLD_MM

# Find transitions (False -> True is start, True -> False is end)
df['transition'] = df['active'].astype(int).diff()

starts = df.index[df['transition'] == 1].tolist()
ends = df.index[df['transition'] == -1].tolist()

# Handle edge cases (started active or ended active)
if len(ends) < len(starts):
    ends.append(len(df) - 1)
if len(starts) > len(ends): # Should be covered above, but for safety
    starts = starts[:len(ends)]

print(f"Detected {len(starts)} motion cycles.")

# --- PLOTTING SETUP ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
fig.suptitle(f'Motion Dynamics Overlay ({len(starts)} cycles)', fontsize=16)

colors = plt.cm.viridis(np.linspace(0, 1, len(starts)))

for i, (start_idx, end_idx) in enumerate(zip(starts, ends)):
    # Add a little padding before and after to see the lift-off
    pad = 5
    s = max(0, start_idx - pad)
    e = min(len(df), end_idx + pad)
    
    segment = df.iloc[s:e].copy()
    
    # Normalize Time: Set t=0 to the start of the movement
    # We use the actual trigger point 'start_idx' for alignment
    start_time = df.loc[start_idx, 'time_s']
    segment['norm_time'] = segment['time_s'] - start_time
    
    # Calculate Velocity (mm/s) -> derivative of position
    # dy / dx
    segment['velocity'] = segment['position_mm'].diff() / segment['time_s'].diff()
    
    # Apply a slight smoothing to velocity to remove differentiation noise
    segment['velocity_smooth'] = segment['velocity'].rolling(window=3).mean()

    # Plot Position
    ax1.plot(segment['norm_time'], segment['position_mm'], label=f'Cycle {i+1}', color=colors[i], linewidth=1.5, alpha=0.8)

    # Plot Velocity
    ax2.plot(segment['norm_time'], segment['velocity_smooth'], label=f'Cycle {i+1}', color=colors[i], linewidth=1.5, alpha=0.8)

# Formatting Position Plot
ax1.set_title('Position vs Normalized Time (Repeatability Check)')
ax1.set_xlabel('Time since movement start (s)')
ax1.set_ylabel('Position (mm)')
ax1.grid(True, which='both', linestyle='--', alpha=0.5)
ax1.legend(loc='upper right', fontsize='small')

# Formatting Velocity Plot
ax2.set_title('Velocity Profile (Smoothness Check)')
ax2.set_xlabel('Time since movement start (s)')
ax2.set_ylabel('Velocity (mm/s)')
ax2.grid(True, which='both', linestyle='--', alpha=0.5)
# Add a zero line for velocity
ax2.axhline(0, color='black', linewidth=1, alpha=0.5)

plt.tight_layout()
plt.show()