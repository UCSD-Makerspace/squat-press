import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

filename = 'csv/sensor1_20260224_145305.csv'
try:
    df = pd.read_csv(filename)
except FileNotFoundError:
    print(f"Error: {filename} not found.")
    exit()

# Load ground truth data from manual ruler measurements
ground_truth_filename = 'csv/2026.02.24 golden truth (2).csv'
try:
    ground_truth = pd.read_csv(ground_truth_filename)
    has_ground_truth = True
except FileNotFoundError:
    print(f"Warning: {ground_truth_filename} not found. Proceeding without ground truth.")
    ground_truth = None
    has_ground_truth = False

# --- SEGMENTATION ---
# New cycle segmentation: detect when `time_s` resets/decreases between rows.
# This matches the new logging method where each cycle's samples start at ~0s.
PEAK_THRESHOLD_MM = 19.5

# Ensure numeric times
df['time_s'] = pd.to_numeric(df['time_s'], errors='coerce')

# Compute time differences between consecutive samples; a large negative jump indicates a new cycle
df['time_diff'] = df['time_s'].diff().fillna(0)
# Threshold to detect a reset to ~0.0 (choose -0.5s to be conservative)
RESET_THRESHOLD = -0.5
df['cycle_break'] = df['time_diff'] < RESET_THRESHOLD
df['cycle_id'] = df['cycle_break'].cumsum()

print(f"Detected {df['cycle_id'].nunique()} raw cycles (including any incomplete ones).")

# Build candidate cycles (start, end indices) from cycle groups
candidate_cycles = []
for cid, grp in df.groupby('cycle_id'):
    start_idx = grp.index[0]
    end_idx = grp.index[-1]
    candidate_cycles.append((start_idx, end_idx))

# --- FILTER ---
starts_filtered = []
ends_filtered = []

if candidate_cycles:
    for start_idx, end_idx in candidate_cycles:
        if start_idx >= len(df) or end_idx < start_idx:
            continue
        segment = df.loc[start_idx:end_idx].copy()
        if segment.empty:
            continue
        peak_position = segment['position_mm'].max()
        cycle_duration = segment['time_s'].iloc[-1] - segment['time_s'].iloc[0]
        if peak_position >= PEAK_THRESHOLD_MM and cycle_duration > 0:
            starts_filtered.append(start_idx)
            ends_filtered.append(end_idx)

cycles = len(starts_filtered)
print(f"Filtered to {cycles} valid cycles.\n")

if cycles == 0:
    print("No valid cycles found after filtering. Exiting.")
    exit()

# --- OVERLAY CYCLES ---
N_CYCLES_TO_SHOW = "ALL"  # Set to integer (e.g., 10, 50) or "ALL" for all cycles

if N_CYCLES_TO_SHOW == "ALL":
    cycles_to_plot = cycles
    title_suffix = f"All {cycles} Cycles"
else:
    cycles_to_plot = min(N_CYCLES_TO_SHOW, cycles)
    title_suffix = f"First {cycles_to_plot} Cycles"

fig, ax = plt.subplots(figsize=(14, 7))

colors = plt.cm.viridis(np.linspace(0, 1, cycles_to_plot))

legend_labels = []
all_y_list = []
max_norm_time = 0.0
for i in range(cycles_to_plot):
    start_idx = starts_filtered[i]
    end_idx = ends_filtered[i]
    segment = df.iloc[start_idx:end_idx + 1].copy()

    # Normalize time to start at 0
    start_time = segment['time_s'].iloc[0]
    segment['norm_time'] = segment['time_s'] - start_time

    ax.plot(segment['norm_time'], segment['position_mm'], 
            linewidth=1.5, alpha=0.7, color=colors[i])
    ax.scatter(segment['norm_time'], segment['position_mm'], 
               s=8, alpha=0.5, color=colors[i])

    all_y_list.append(segment['position_mm'].values)
    if not segment['norm_time'].empty:
        max_norm_time = max(max_norm_time, segment['norm_time'].max())

    # Build compact legend labels
    if i < 10 or i >= cycles_to_plot - 10:
        legend_labels.append(f'Cycle {i}')
    elif i == 10:
        legend_labels.append('...')

# --- OVERLAY GROUND TRUTH ---
if has_ground_truth:
    print(f"\nGround Truth Data:")
    print(ground_truth)
    
    # Compute average first-movement time across all cycles
    first_move_times = []
    for i in range(cycles_to_plot):
        seg = df.iloc[starts_filtered[i]:ends_filtered[i] + 1].copy()
        moving = seg[seg['position_mm'] > 0.5]['time_s']
        if not moving.empty:
            first_move_times.append(moving.iloc[0])
    
    avg_first_move = np.mean(first_move_times) if first_move_times else 0.0
    print(f"Average first-move time offset: {avg_first_move:.4f}s")
    
    ground_truth['norm_time'] = (ground_truth['frame'] - 1) / 240.0 + avg_first_move
    
    ax.plot(ground_truth['norm_time'], ground_truth['mm'], 
            linewidth=4, color='red', alpha=0.9, label='Ground Truth (Ruler)', zorder=10)
    ax.scatter(ground_truth['norm_time'], ground_truth['mm'], 
               s=40, color='red', alpha=0.8, marker='X', edgecolors='darkred', linewidth=1, zorder=11)

ax.set_xlabel('Time since cycle start (s)', fontsize=11)
ax.set_ylabel('Position (mm)', fontsize=11)
ax.set_title(f'{title_suffix} Overlayed (Normalized Time) with Ground Truth', fontsize=12)
ax.grid(True, alpha=0.3)

# Build legend with ground truth
if cycles_to_plot > 20:
    handles = []
    labels = []
    for i in range(10):
        h = plt.Line2D([0], [0], color=colors[i], linewidth=1.5, alpha=0.7)
        handles.append(h)
        labels.append(f'Cycle {i}')
    
    labels.append('...')
    handles.append(plt.Line2D([0], [0], color='gray', linewidth=1, linestyle='--', alpha=0.5))
    
    for i in range(cycles_to_plot - 10, cycles_to_plot):
        h = plt.Line2D([0], [0], color=colors[i], linewidth=1.5, alpha=0.7)
        handles.append(h)
        labels.append(f'Cycle {i}')
    
    if has_ground_truth:
        h_truth = plt.Line2D([0], [0], color='red', linewidth=4, alpha=0.9, marker='X', markersize=6)
        handles.append(h_truth)
        labels.append('Ground Truth (Ruler)')
    
    ax.legend(handles, labels, loc='upper left', fontsize=9, ncol=1)
else:
    handles = [plt.Line2D([0], [0], color=colors[i], linewidth=1.5, alpha=0.7) for i in range(cycles_to_plot)]
    labels = [f'Cycle {i}' for i in range(cycles_to_plot)]
    
    if has_ground_truth:
        h_truth = plt.Line2D([0], [0], color='red', linewidth=4, alpha=0.9, marker='X', markersize=6)
        handles.append(h_truth)
        labels.append('Ground Truth (Ruler)')
    
    ax.legend(handles, labels, loc='upper left', fontsize=9)

# Set x limits from 0 to max normalized time (with small margin)
if max_norm_time <= 0:
    ax.set_xlim(0, 1.2)
else:
    ax.set_xlim(0, max(1.2, max_norm_time * 1.05))

all_y = np.concatenate(all_y_list) if all_y_list else np.array([0.0])
y_min, y_max = all_y.min(), all_y.max()
y_margin = (y_max - y_min) * 0.1 if (y_max - y_min) > 0 else 1.0
ax.set_ylim(y_min - y_margin, y_max + y_margin)

outname = f'sensor_{cycles_to_plot}_cycles.png'
fig.savefig(outname, dpi=200, bbox_inches='tight')
print(f"\nSaved overlay plot to {outname}")
plt.show()