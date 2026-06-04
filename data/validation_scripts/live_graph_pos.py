"""
live_graph_pos.py — Live scrolling position graph for the linear sensor
=======================================================================
Plug the sensor USB directly into this laptop.
Shows the last WINDOW_S seconds of position data in real time.

Line colour:
  blue  — below threshold, or above threshold but lift not yet valid
  green — above threshold AND held for >= min_lift_s  (valid lift confirmed)

Hot-swap: unplug the sensor at any time — the graph shows a "no sensor"
overlay and automatically reconnects when it's plugged back in.

Start/Stop buttons (or S / E keys) toggle CSV recording. On Stop a
file-save dialog opens and session stats are shown in the UI.

Bottom-left controls let you edit the lift threshold (mm) and minimum
valid lift duration (s) without restarting the script.

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button, TextBox
from components.LinearSensor import interpolate

BAUD_RATE   = 115200
WINDOW_S    = 10.0
MAX_PTS     = 6000
HZ_SMOOTH_N = 30

# ── Shared sensor state ───────────────────────────────────────────────────────

_lock      = threading.Lock()
_times     = deque(maxlen=MAX_PTS)
_pos       = deque(maxlen=MAX_PTS)
_raw       = deque(maxlen=MAX_PTS)
_connected = False

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
        if ser is None:
            candidates = [p.device for p in serial.tools.list_ports.comports()]
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

# ── Line colouring ────────────────────────────────────────────────────────────

def _split_colors(ts_win, ps_win, threshold, min_lift_s):
    """
    Split position data into two masked arrays for line colouring.
      blue  — below threshold, or above threshold but run duration < min_lift_s
      green — above threshold AND the contiguous run >= min_lift_s (valid lift)
    """
    _nan = float('nan')
    n        = len(ps_win)
    ps_blue  = list(ps_win)
    ps_green = [_nan] * n

    i = 0
    while i < n:
        if ps_win[i] >= threshold:
            run_start = i
            while i < n and ps_win[i] >= threshold:
                i += 1
            run_end  = i
            duration = ts_win[run_end - 1] - ts_win[run_start]
            if duration >= min_lift_s:
                for j in range(run_start, run_end):
                    ps_green[j] = ps_win[j]
                    ps_blue[j]  = _nan
        else:
            i += 1

    return ps_blue, ps_green

# ── Session stats ─────────────────────────────────────────────────────────────

def _session_stats(buffer, threshold, min_lift_s):
    if len(buffer) < 2:
        return 0, 0.0, 0.0

    duration = buffer[-1][0] - buffer[0][0]
    avg_hz   = len(buffer) / duration if duration > 0 else 0.0

    lifts, peak_counts = 0, []
    in_lift = False
    lift_start_t = lift_above_n = 0

    for t, mm, _ in buffer:
        if mm >= threshold:
            if not in_lift:
                in_lift = True; lift_start_t = t; lift_above_n = 1
            else:
                lift_above_n += 1
        elif in_lift:
            if (t - lift_start_t) >= min_lift_s:
                lifts += 1; peak_counts.append(lift_above_n)
            in_lift = False

    if in_lift and (buffer[-1][0] - lift_start_t) >= min_lift_s:
        lifts += 1; peak_counts.append(lift_above_n)

    mean_peak = sum(peak_counts) / len(peak_counts) if peak_counts else 0.0
    return lifts, round(avg_hz, 1), round(mean_peak, 1)

# ── CSV save ──────────────────────────────────────────────────────────────────

def _save_csv(buffer):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw(); root.lift()
    path = filedialog.asksaveasfilename(
        title="Save recording as…",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile=f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    )
    root.destroy()
    if not path:
        print("Save cancelled."); return
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "position_mm", "raw_value"])
        w.writerows(buffer)
    print(f"Saved {len(buffer)} rows → {path}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _recording, _rec_buffer, _rec_t0

    port = _pick_port()
    default_threshold = float(
        input("Lift detection threshold (mm) [19.0]: ").strip() or 19.0
    )
    default_min_lift = float(
        input("Minimum time above threshold for a valid lift (s) [0.040]: ").strip() or 0.040
    )
    threshold  = [default_threshold]
    min_lift_s = [default_min_lift]

    print(f"Starting sensor reader (port hint: {port}) ...")
    threading.Thread(target=_reader, args=(port,), daemon=True).start()

    fig, (ax_pos, ax_hz) = plt.subplots(2, 1, figsize=(12, 7), sharex=False)
    fig.patch.set_facecolor('#0d0d0d')
    fig.subplots_adjust(bottom=0.15, hspace=0.35)
    fig.canvas.manager.set_window_title('Live Sensor Position')

    for ax in (ax_pos, ax_hz):
        ax.set_facecolor('#141414')
        ax.tick_params(colors='#888', right=True, labelright=True)
        for spine in ax.spines.values():
            spine.set_edgecolor('#333')
        ax.grid(True, alpha=0.15, color='#555')

    # position subplot
    (line_blue,)  = ax_pos.plot([], [], color='#4a9eff', linewidth=1.5)
    (line_green,) = ax_pos.plot([], [], color='#4ade80', linewidth=1.5)
    hline = ax_pos.axhline(threshold[0], color='#ff6b6b', linestyle='--',
                            linewidth=1.0, label=f'Detection threshold')
    ax_pos.set_xlim(0, WINDOW_S)
    ax_pos.set_ylim(-0.5, 26)
    ax_pos.set_ylabel('Position (mm)', color='#aaa')
    ax_pos.set_title('Live Sensor Position', color='#ddd', pad=8)
    ax_pos.legend(fontsize=8, facecolor='#1a1a1a', labelcolor='#ccc', edgecolor='#333')

    live_val_text = ax_pos.text(
        0.02, 0.95, 'Live Linear Sensor Position: — mm',
        transform=ax_pos.transAxes, fontsize=10, color='#4a9eff',
        va='top', fontfamily='monospace',
    )
    avg_val_text = ax_pos.text(
        0.02, 0.83, 'Last 0.1 sec average: — mm',
        transform=ax_pos.transAxes, fontsize=9, color='#aaaaaa',
        va='top', fontfamily='monospace',
    )

    # hz subplot
    (line_hz,) = ax_hz.plot([], [], color='#a78bfa', linewidth=1.2)
    ax_hz.set_xlim(0, WINDOW_S)
    ax_hz.set_ylim(0, 350)
    ax_hz.set_xlabel('Time (s)', color='#aaa')
    ax_hz.set_ylabel('Sampling rate (Hz)', color='#aaa')
    ax_hz.set_title('Live Sampling Frequency', color='#ddd', pad=8)

    # disconnection overlay
    _ov_kw = dict(ha='center', va='center', fontsize=11, color='#ff6b6b', visible=False,
                  bbox=dict(boxstyle='round,pad=0.6', facecolor='#111111', edgecolor='#444', alpha=0.92))
    overlay_pos = ax_pos.text(0.5, 0.5, 'No linear sensor detected\nPlease plug in the USB',
                               transform=ax_pos.transAxes, **_ov_kw)
    overlay_hz  = ax_hz.text(0.5, 0.5, '', transform=ax_hz.transAxes, **_ov_kw)

    rec_text   = fig.text(0.5, 0.075, '', ha='center', va='center',
                          fontsize=9, color='#888', fontfamily='monospace')
    stats_text = fig.text(0.72, 0.042, '', ha='left', va='center',
                          fontsize=8, color='#b0b0b0', fontfamily='monospace',
                          linespacing=1.6)

    # ── Bottom controls ───────────────────────────────────────────────────────
    btn_style = dict(color='#1e1e1e', hovercolor='#2a2a2a')
    tb_style  = dict(color='#1a1a1a', hovercolor='#222222')

    # Threshold TextBox
    fig.text(0.010, 0.042, 'Threshold\n(mm):', ha='left', va='center',
             fontsize=7.5, color='#888', fontfamily='monospace')
    ax_tb_thresh = fig.add_axes([0.082, 0.028, 0.055, 0.032])
    tb_thresh = TextBox(ax_tb_thresh, '', initial=str(default_threshold), **tb_style)
    tb_thresh.text_disp.set_color('#cccccc')
    tb_thresh.text_disp.set_fontsize(9)

    # Min lift TextBox
    fig.text(0.148, 0.042, 'Min lift\n(s):', ha='left', va='center',
             fontsize=7.5, color='#888', fontfamily='monospace')
    ax_tb_lift = fig.add_axes([0.208, 0.028, 0.055, 0.032])
    tb_lift = TextBox(ax_tb_lift, '', initial=str(default_min_lift), **tb_style)
    tb_lift.text_disp.set_color('#cccccc')
    tb_lift.text_disp.set_fontsize(9)

    def on_thresh_submit(text):
        try:
            v = float(text)
            if 0 < v <= 25:
                threshold[0] = v
                hline.set_ydata([v, v])
                fig.canvas.draw_idle()
                print(f"Threshold updated to {v:.1f} mm")
        except ValueError:
            pass

    def on_min_lift_submit(text):
        try:
            v = float(text)
            if v > 0:
                min_lift_s[0] = v
                print(f"Min lift time updated to {v:.3f} s")
        except ValueError:
            pass

    tb_thresh.on_submit(on_thresh_submit)
    tb_lift.on_submit(on_min_lift_submit)

    # Start / Stop buttons
    ax_start = fig.add_axes([0.29, 0.022, 0.155, 0.04])
    ax_stop  = fig.add_axes([0.46, 0.022, 0.13,  0.04])
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
            _rec_buffer = []; _rec_t0 = time.perf_counter(); _recording = True
        stats_text.set_text('')
        btn_start.label.set_text('Recording in progress…')
        btn_start.label.set_color('#555555')
        btn_start.color = btn_start.hovercolor = '#161616'
        ax_start.set_facecolor('#161616')
        rec_text.set_text('● Recording…'); rec_text.set_color('#ff6b6b')
        fig.canvas.draw_idle()
        print("Recording started.")

    def _do_stop():
        global _recording
        with _rec_lock:
            if not _recording:
                return
            _recording = False
            snapshot = list(_rec_buffer)
        btn_start.label.set_text('Start Recording')
        btn_start.label.set_color('#cccccc')
        btn_start.color = '#1e1e1e'; btn_start.hovercolor = '#2a2a2a'
        ax_start.set_facecolor('#1e1e1e')
        n_lifts, avg_hz, mean_pk = _session_stats(snapshot, threshold[0], min_lift_s[0])
        stats_text.set_text(
            f"Lifts detected:          {n_lifts}\n"
            f"Avg sampling rate:    {avg_hz} Hz\n"
            f"Mean samples ≥ threshold: {mean_pk}"
        )
        rec_text.set_text(f'{len(snapshot)} samples recorded — see file dialog')
        rec_text.set_color('#888')
        fig.canvas.draw_idle()
        print(f"Recording stopped ({len(snapshot)} samples). Opening save dialog…")
        threading.Thread(target=_save_csv, args=(snapshot,), daemon=True).start()

    btn_start.on_clicked(lambda _e: _do_start())
    btn_stop.on_clicked( lambda _e: _do_stop())

    def on_key(event):
        if event.key == 's':   _do_start()
        elif event.key == 'e': _do_stop()
    fig.canvas.mpl_connect('key_press_event', on_key)

    # ── Animation ─────────────────────────────────────────────────────────────

    _prev_connected = [True]

    def update(_frame):
        with _lock:
            connected = _connected
            if not _times:
                overlay_pos.set_visible(True); overlay_hz.set_visible(False)
                return (line_blue, line_green, line_hz, overlay_pos, overlay_hz,
                        live_val_text, avg_val_text)
            ts = list(_times)
            ps = list(_pos)

        if connected != _prev_connected[0]:
            _prev_connected[0] = connected
            fig.canvas.manager.set_window_title(
                'Live Sensor Position' if connected else 'Live Sensor Position — DISCONNECTED'
            )

        overlay_pos.set_visible(not connected)
        overlay_hz.set_visible(False)

        if not connected:
            live_val_text.set_text('Live Linear Sensor Position: — mm')
            avg_val_text.set_text('Last 0.1 sec average: — mm')
            return (line_blue, line_green, line_hz, overlay_pos, overlay_hz,
                    live_val_text, avg_val_text)

        t_now  = ts[-1]
        cutoff = t_now - WINDOW_S

        start = 0
        for i, t in enumerate(ts):
            if t >= cutoff:
                start = i; break

        ts_win = ts[start:]
        ps_win = ps[start:]

        ps_b, ps_g = _split_colors(ts_win, ps_win, threshold[0], min_lift_s[0])
        line_blue.set_data(ts_win, ps_b)
        line_green.set_data(ts_win, ps_g)
        ax_pos.set_xlim(t_now - WINDOW_S, t_now)

        live_val_text.set_text(f'Live Linear Sensor Position: {ps[-1]:.2f} mm')
        avg_samp = [ps[i] for i, t in enumerate(ts) if t >= t_now - 0.1]
        if avg_samp:
            avg_val_text.set_text(
                f'Last 0.1 sec average: {sum(avg_samp)/len(avg_samp):.2f} mm'
            )

        N = HZ_SMOOTH_N
        if len(ts) > N:
            hz_ts   = ts[N:]
            hz_vals = [N / (ts[i] - ts[i - N]) for i in range(N, len(ts))]
            hz_start = 0
            for i, t in enumerate(hz_ts):
                if t >= cutoff:
                    hz_start = i; break
            line_hz.set_data(hz_ts[hz_start:], hz_vals[hz_start:])
        ax_hz.set_xlim(t_now - WINDOW_S, t_now)

        return (line_blue, line_green, line_hz, overlay_pos, overlay_hz,
                live_val_text, avg_val_text)

    _ani = animation.FuncAnimation(fig, update, interval=50, blit=True)
    plt.show()

if __name__ == "__main__":
    main()
