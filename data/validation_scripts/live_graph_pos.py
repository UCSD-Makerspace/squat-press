"""
live_graph_pos.py — Live scrolling position graph for the linear sensor
=======================================================================
Plug the sensor USB directly into this laptop.
Shows the last WINDOW_S seconds of position data in real time.

Start/Stop buttons toggle CSV recording independently of the live graph.
On Stop a file-save dialog opens to choose where to write the CSV.

Usage:
    python live_graph_pos.py              # auto-detect or prompt for port
    python live_graph_pos.py COM3         # Windows
    python live_graph_pos.py /dev/ttyACM0 # Linux / Pi
"""

import csv
import sys
import time
import threading
from collections import deque
from datetime import datetime

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button

BAUD_RATE   = 115200
WINDOW_S    = 10.0   # seconds of history shown in the scrolling plot
PEAK_MM     = 19.0   # horizontal reference line
MAX_PTS     = 6000   # ring buffer (~30 s at 200 Hz)
HZ_SMOOTH_N = 30     # rolling window size for Hz estimate (samples)

CALIBRATION_TABLE = [
    (0.000, 10615), (1.000, 10444), (2.000, 10284), (3.000, 10136),
    (4.000,  9992), (5.000,  9826), (6.000,  9644), (7.000,  9556),
    (8.000,  9463), (9.000,  9184),(10.000,  8982),(11.000,  8732),
    (12.000, 8457),(13.000,  8289),(14.000,  8125),(15.000,  7959),
    (16.000, 7789),(17.000,  7637),(18.000,  7447),(19.000,  7267),
    (20.000, 7042),(21.000,  6865),(22.000,  6684),(23.000,  6471),
    (24.000, 6254),(25.000,  6114),
]

def interpolate(raw):
    t = CALIBRATION_TABLE
    if raw >= t[0][1]:  return t[0][0]
    if raw <= t[-1][1]: return t[-1][0]
    for i in range(len(t) - 1):
        mm1, r1 = t[i]; mm2, r2 = t[i+1]
        if r2 <= raw <= r1:
            return mm1 + (raw - r1) / (r2 - r1) * (mm2 - mm1)
    return None

# ── Shared sensor state ───────────────────────────────────────────────────────

_lock  = threading.Lock()
_times = deque(maxlen=MAX_PTS)
_pos   = deque(maxlen=MAX_PTS)
_raw   = deque(maxlen=MAX_PTS)

# ── Recording state ───────────────────────────────────────────────────────────

_rec_lock   = threading.Lock()
_recording  = False
_rec_buffer = []   # list of (time_s, position_mm, raw_value)
_rec_t0     = None

# ── Serial reader thread ──────────────────────────────────────────────────────

def _reader(port):
    ser = serial.Serial(port, BAUD_RATE, timeout=0.02)
    t0  = time.perf_counter()
    while True:
        ser.write(b'F')
        resp = ser.readline().decode('ascii', errors='replace').strip()
        if resp:
            try:
                raw_val = int(resp.split()[0], 16)
                mm      = interpolate(raw_val)
                if mm is not None:
                    t_now = time.perf_counter()
                    with _lock:
                        _times.append(t_now - t0)
                        _pos.append(mm)
                        _raw.append(raw_val)
                    with _rec_lock:
                        if _recording:
                            _rec_buffer.append((
                                round(t_now - _rec_t0, 5),
                                round(mm, 4),
                                raw_val,
                            ))
            except Exception:
                pass

# ── Port picker ───────────────────────────────────────────────────────────────

def _pick_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        raise RuntimeError(
            "No serial ports detected. Plug in the sensor and retry, "
            "or pass the port as an argument: python live_graph_pos.py COM3"
        )
    if len(ports) == 1:
        print(f"Auto-selected port: {ports[0]}")
        return ports[0]
    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p}")
    idx = int(input("Select port number: ").strip())
    return ports[idx]

# ── CSV save ──────────────────────────────────────────────────────────────────

def _save_csv(buffer):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.lift()
    default_name = f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path = filedialog.asksaveasfilename(
        title="Save recording as…",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile=default_name,
    )
    root.destroy()
    if not path:
        print("Save cancelled.")
        return
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "position_mm", "raw_value"])
        w.writerows(buffer)
    print(f"Saved {len(buffer)} rows → {path}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _recording, _rec_buffer, _rec_t0

    port = _pick_port()
    print(f"Connecting to {port} ...")
    threading.Thread(target=_reader, args=(port,), daemon=True).start()

    # leave room at bottom for buttons
    fig, (ax_pos, ax_hz) = plt.subplots(2, 1, figsize=(11, 7), sharex=False)
    fig.patch.set_facecolor('#0d0d0d')
    fig.subplots_adjust(bottom=0.13, hspace=0.35)

    for ax in (ax_pos, ax_hz):
        ax.set_facecolor('#141414')
        ax.tick_params(colors='#888')
        for spine in ax.spines.values():
            spine.set_edgecolor('#333')
        ax.grid(True, alpha=0.15, color='#555')

    # position subplot
    (line_pos,) = ax_pos.plot([], [], color='#4a9eff', linewidth=1.5)
    ax_pos.axhline(PEAK_MM, color='#ff6b6b', linestyle='--', linewidth=1.0,
                   label=f'{PEAK_MM:.0f} mm detection threshold')
    ax_pos.set_xlim(0, WINDOW_S)
    ax_pos.set_ylim(-0.5, 26)
    ax_pos.set_ylabel('Position (mm)', color='#aaa')
    ax_pos.set_title('Live Sensor Position', color='#ddd', pad=8)
    ax_pos.legend(fontsize=8, facecolor='#1a1a1a', labelcolor='#ccc', edgecolor='#333')

    # hz subplot
    (line_hz,) = ax_hz.plot([], [], color='#a78bfa', linewidth=1.2)
    ax_hz.set_xlim(0, WINDOW_S)
    ax_hz.set_ylim(0, 350)
    ax_hz.set_xlabel('Time (s)', color='#aaa')
    ax_hz.set_ylabel('Sampling rate (Hz)', color='#aaa')
    ax_hz.set_title('Live Sampling Frequency', color='#ddd', pad=8)

    # recording status text
    rec_text = fig.text(0.5, 0.055, '', ha='center', va='center',
                        fontsize=9, color='#888',
                        fontfamily='monospace')

    # ── Buttons ───────────────────────────────────────────────────────────────
    btn_style = dict(color='#1e1e1e', hovercolor='#2a2a2a')

    ax_start = fig.add_axes([0.32, 0.02, 0.14, 0.04])
    ax_stop  = fig.add_axes([0.54, 0.02, 0.14, 0.04])
    btn_start = Button(ax_start, 'Start Recording', **btn_style)
    btn_stop  = Button(ax_stop,  'Stop Recording',  **btn_style)

    for btn in (btn_start, btn_stop):
        btn.label.set_fontsize(8.5)
        btn.label.set_color('#cccccc')

    def on_start(_event):
        global _recording, _rec_buffer, _rec_t0
        with _rec_lock:
            if _recording:
                return
            _rec_buffer = []
            _rec_t0     = time.perf_counter()
            _recording  = True
        rec_text.set_text('● Recording…')
        rec_text.set_color('#ff6b6b')
        print("Recording started.")

    def on_stop(_event):
        global _recording
        with _rec_lock:
            if not _recording:
                return
            _recording = False
            snapshot   = list(_rec_buffer)
        rec_text.set_text(f'Saved {len(snapshot)} samples — see file dialog')
        rec_text.set_color('#888')
        print(f"Recording stopped ({len(snapshot)} samples). Opening save dialog…")
        threading.Thread(target=_save_csv, args=(snapshot,), daemon=True).start()

    btn_start.on_clicked(on_start)
    btn_stop.on_clicked(on_stop)

    # ── Animation ─────────────────────────────────────────────────────────────

    def update(_frame):
        with _lock:
            if not _times:
                return (line_pos, line_hz)
            ts = list(_times)
            ps = list(_pos)

        t_now  = ts[-1]
        cutoff = t_now - WINDOW_S

        start = 0
        for i, t in enumerate(ts):
            if t >= cutoff:
                start = i
                break

        line_pos.set_data(ts[start:], ps[start:])
        ax_pos.set_xlim(t_now - WINDOW_S, t_now)

        N = HZ_SMOOTH_N
        if len(ts) > N:
            hz_ts   = ts[N:]
            hz_vals = [N / (ts[i] - ts[i - N]) for i in range(N, len(ts))]
            hz_start = 0
            for i, t in enumerate(hz_ts):
                if t >= cutoff:
                    hz_start = i
                    break
            line_hz.set_data(hz_ts[hz_start:], hz_vals[hz_start:])
        ax_hz.set_xlim(t_now - WINDOW_S, t_now)

        return (line_pos, line_hz)

    _ani = animation.FuncAnimation(fig, update, interval=50, blit=True)
    plt.show()

if __name__ == "__main__":
    main()
