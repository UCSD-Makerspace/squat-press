"""
live_graph_pos.py — Live scrolling position graph for the linear sensor
=======================================================================
Plug the sensor USB directly into this laptop.
Shows the last WINDOW_S seconds of position data in real time.

Usage:
    python live_graph_pos.py              # auto-detect or prompt for port
    python live_graph_pos.py COM3         # Windows
    python live_graph_pos.py /dev/ttyACM0 # Linux / Pi
"""

import sys
import time
import threading
from collections import deque

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation

BAUD_RATE = 115200
WINDOW_S  = 10.0   # seconds of history shown in the scrolling plot
PEAK_MM   = 19.0   # horizontal reference line
MAX_PTS   = 6000   # ring buffer (~30 s at 200 Hz)

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

HZ_SMOOTH_N = 30   # rolling window size for Hz estimate (samples)

_lock  = threading.Lock()
_times = deque(maxlen=MAX_PTS)
_pos   = deque(maxlen=MAX_PTS)

def _reader(port):
    ser = serial.Serial(port, BAUD_RATE, timeout=0.02)
    t0  = time.perf_counter()
    while True:
        ser.write(b'F')
        resp = ser.readline().decode('ascii', errors='replace').strip()
        if resp:
            try:
                raw = int(resp.split()[0], 16)
                mm  = interpolate(raw)
                if mm is not None:
                    with _lock:
                        _times.append(time.perf_counter() - t0)
                        _pos.append(mm)
            except Exception:
                pass

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

def main():
    port = _pick_port()
    print(f"Connecting to {port} ...")

    threading.Thread(target=_reader, args=(port,), daemon=True).start()

    fig, (ax_pos, ax_hz) = plt.subplots(2, 1, figsize=(11, 7), sharex=False)
    fig.patch.set_facecolor('#0d0d0d')

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

    fig.tight_layout(pad=2.0)

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

        ts_win = ts[start:]
        ps_win = ps[start:]
        line_pos.set_data(ts_win, ps_win)
        ax_pos.set_xlim(t_now - WINDOW_S, t_now)

        # Hz: N / (t[i] - t[i-N]) — averages out per-sample jitter
        N = HZ_SMOOTH_N
        if len(ts) > N:
            hz_ts = ts[N:]
            hz_vals = [N / (ts[i] - ts[i - N]) for i in range(N, len(ts))]
            # trim to visible window
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
