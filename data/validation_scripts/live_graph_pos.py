"""
live_graph_pos.py — Live scrolling position graph for the linear sensor
=======================================================================
Plug the sensor USB directly into this laptop.
Shows the last WINDOW_S seconds of position data in real time.

Hot-swap: unplug the sensor at any time — the graph shows a "no sensor"
overlay and automatically reconnects when it's plugged back in.

Start/Stop buttons (or S / E keys) toggle CSV recording independently
of the live graph. On Stop a file-save dialog opens.

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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button
from components.LinearSensor import interpolate

BAUD_RATE   = 115200
WINDOW_S    = 10.0   # seconds of history shown in the scrolling plot
PEAK_MM     = 19.0   # horizontal reference line
MAX_PTS     = 6000   # ring buffer (~30 s at 200 Hz)
HZ_SMOOTH_N = 30     # rolling window size for Hz estimate (samples)

# ── Shared sensor state ───────────────────────────────────────────────────────

_lock      = threading.Lock()
_times     = deque(maxlen=MAX_PTS)
_pos       = deque(maxlen=MAX_PTS)
_raw       = deque(maxlen=MAX_PTS)
_connected = False    # True when sensor is actively streaming data

# ── Recording state ───────────────────────────────────────────────────────────

_rec_lock   = threading.Lock()
_recording  = False
_rec_buffer = []
_rec_t0     = None

# ── Serial reader / reconnect loop ────────────────────────────────────────────

def _reader(initial_port):
    global _connected
    port = initial_port
    ser  = None
    t0   = time.perf_counter()

    while True:
        # ── Connect / reconnect ───────────────────────────────────────────────
        if ser is None:
            candidates = [p.device for p in serial.tools.list_ports.comports()]
            # prefer the original port, then try anything available
            ordered = ([port] if port in candidates else []) + \
                      [p for p in candidates if p != port]
            for candidate in ordered:
                try:
                    ser  = serial.Serial(candidate, BAUD_RATE, timeout=0.02)
                    port = candidate
                    t0   = time.perf_counter()
                    with _lock:
                        _times.clear(); _pos.clear(); _raw.clear()
                        _connected = True
                    print(f"Sensor connected on {port}")
                    break
                except (serial.SerialException, OSError):
                    pass
            if ser is None:
                time.sleep(0.5)
                continue

        # ── Read sample ───────────────────────────────────────────────────────
        try:
            ser.write(b'F')
            resp = ser.readline().decode('ascii', errors='replace').strip()
            if resp:
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
        except (serial.SerialException, OSError):
            print(f"Sensor disconnected from {port}.")
            with _lock:
                _connected = False
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(0.5)

# ── Port picker ───────────────────────────────────────────────────────────────

def _pick_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        print("No serial ports detected — will keep scanning until sensor is plugged in.")
        return "__scan__"
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
    print(f"Starting sensor reader (port hint: {port}) ...")
    threading.Thread(target=_reader, args=(port,), daemon=True).start()

    fig, (ax_pos, ax_hz) = plt.subplots(2, 1, figsize=(11, 7), sharex=False)
    fig.patch.set_facecolor('#0d0d0d')
    fig.subplots_adjust(bottom=0.13, hspace=0.35)
    fig.canvas.manager.set_window_title('Live Sensor Position')

    for ax in (ax_pos, ax_hz):
        ax.set_facecolor('#141414')
        ax.tick_params(colors='#888', right=True, labelright=True)
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

    # disconnection overlay (one per subplot, hidden by default)
    _overlay_kw = dict(
        transform=None, ha='center', va='center', fontsize=11,
        color='#ff6b6b', visible=False,
        bbox=dict(boxstyle='round,pad=0.6', facecolor='#111111',
                  edgecolor='#444', alpha=0.92),
    )
    overlay_pos = ax_pos.text(
        0.5, 0.5, 'No linear sensor detected\nPlease plug in the USB',
        transform=ax_pos.transAxes, **{k: v for k, v in _overlay_kw.items() if k != 'transform'},
    )
    overlay_hz = ax_hz.text(
        0.5, 0.5, '',
        transform=ax_hz.transAxes, **{k: v for k, v in _overlay_kw.items() if k != 'transform'},
    )

    # recording status text
    rec_text = fig.text(0.5, 0.055, '', ha='center', va='center',
                        fontsize=9, color='#888', fontfamily='monospace')

    # ── Buttons ───────────────────────────────────────────────────────────────
    btn_style = dict(color='#1e1e1e', hovercolor='#2a2a2a')

    ax_start = fig.add_axes([0.32, 0.02, 0.16, 0.04])
    ax_stop  = fig.add_axes([0.54, 0.02, 0.14, 0.04])
    btn_start = Button(ax_start, 'Start Recording', **btn_style)
    btn_stop  = Button(ax_stop,  'Stop Recording',  **btn_style)

    for btn in (btn_start, btn_stop):
        btn.label.set_fontsize(8.5)
        btn.label.set_color('#cccccc')

    def _do_start():
        global _recording, _rec_buffer, _rec_t0
        with _rec_lock:
            if _recording:
                return
            _rec_buffer = []
            _rec_t0     = time.perf_counter()
            _recording  = True
        btn_start.label.set_text('Recording in progress…')
        btn_start.label.set_color('#555555')
        btn_start.color      = '#161616'
        btn_start.hovercolor = '#161616'
        ax_start.set_facecolor('#161616')
        fig.canvas.draw_idle()
        rec_text.set_text('● Recording…')
        rec_text.set_color('#ff6b6b')
        print("Recording started.")

    def _do_stop():
        global _recording
        with _rec_lock:
            if not _recording:
                return
            _recording = False
            snapshot   = list(_rec_buffer)
        btn_start.label.set_text('Start Recording')
        btn_start.label.set_color('#cccccc')
        btn_start.color      = '#1e1e1e'
        btn_start.hovercolor = '#2a2a2a'
        ax_start.set_facecolor('#1e1e1e')
        fig.canvas.draw_idle()
        rec_text.set_text(f'Saved {len(snapshot)} samples — see file dialog')
        rec_text.set_color('#888')
        print(f"Recording stopped ({len(snapshot)} samples). Opening save dialog…")
        threading.Thread(target=_save_csv, args=(snapshot,), daemon=True).start()

    btn_start.on_clicked(lambda _e: _do_start())
    btn_stop.on_clicked( lambda _e: _do_stop())

    # keyboard shortcuts: S = start, E = end/stop
    def on_key(event):
        if event.key == 's':
            _do_start()
        elif event.key == 'e':
            _do_stop()
    fig.canvas.mpl_connect('key_press_event', on_key)

    # ── Animation ─────────────────────────────────────────────────────────────

    _prev_connected = [True]   # track transitions to avoid redundant redraws

    def update(_frame):
        with _lock:
            connected = _connected
            if not _times:
                overlay_pos.set_visible(True)
                overlay_hz.set_visible(False)
                return (line_pos, line_hz, overlay_pos, overlay_hz)
            ts = list(_times)
            ps = list(_pos)

        # show/hide overlay on connection-state change
        if connected != _prev_connected[0]:
            _prev_connected[0] = connected
            fig.canvas.manager.set_window_title(
                'Live Sensor Position' if connected else 'Live Sensor Position — DISCONNECTED'
            )

        overlay_pos.set_visible(not connected)
        overlay_hz.set_visible(False)   # only clutter position plot with message

        if not connected:
            return (line_pos, line_hz, overlay_pos, overlay_hz)

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

        return (line_pos, line_hz, overlay_pos, overlay_hz)

    _ani = animation.FuncAnimation(fig, update, interval=50, blit=True)
    plt.show()

if __name__ == "__main__":
    main()
