"""
gui.py — optional live scrolling graph for continuous_lift_monitor.

Imported and called by main.py only when --gui flag is passed.
Shows:
  - Blue line  : below threshold, or above threshold but not yet confirmed
  - Green line : confirmed valid lift
  - Orange dot : lift that occurred within pellet_cooldown of the previous one
  - Red dashed : lift_threshold
  - Grey band  : pellet cooldown visualisation (shaded region after each lift)
"""

import threading
import time
from collections import deque

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch

HZ_SMOOTH_N = 30


def _split_colors(ts, ps, threshold, min_lift_s):
    _nan = float('nan')
    n        = len(ps)
    ps_blue  = list(ps)
    ps_green = [_nan] * n

    i = 0
    while i < n:
        if ps[i] >= threshold:
            run_start = i
            while i < n and ps[i] >= threshold:
                i += 1
            run_end  = i
            duration = ts[run_end - 1] - ts[run_start]
            if duration >= min_lift_s:
                for j in range(run_start, run_end):
                    ps_green[j] = ps[j]
                    ps_blue[j]  = _nan
                if run_start > 0:
                    ps_green[run_start - 1] = ps[run_start - 1]
                if run_end < n:
                    ps_green[run_end] = ps[run_end]
        else:
            i += 1

    return ps_blue, ps_green


def run_gui(bus, detector, cfg, stop_event: threading.Event):
    """
    Blocks until the window is closed.  Call from the main thread.
    bus      : SensorBus
    detector : LiftDetector  (for cooldown shading)
    cfg      : Config
    stop_event : set when main wants everything to stop
    """
    window_s = cfg.gui_window_size

    fig, (ax_pos, ax_hz) = plt.subplots(2, 1, figsize=(13, 7), sharex=False)
    fig.patch.set_facecolor('#0d0d0d')
    fig.subplots_adjust(bottom=0.10, hspace=0.38)
    fig.canvas.manager.set_window_title('Continuous Lift Monitor')

    for ax in (ax_pos, ax_hz):
        ax.set_facecolor('#141414')
        ax.tick_params(colors='#888', right=True, labelright=True)
        for spine in ax.spines.values():
            spine.set_edgecolor('#333')
        ax.grid(True, alpha=0.15, color='#555')

    # position lines
    (line_blue,)    = ax_pos.plot([], [], color='#4a9eff', linewidth=1.5)
    (line_green,)   = ax_pos.plot([], [], color='#4ade80', linewidth=1.5)
    hline = ax_pos.axhline(cfg.lift_threshold, color='#ff6b6b',
                           linestyle='--', linewidth=1.0, label='Lift threshold')
    drop_hline = ax_pos.axhline(cfg.drop_threshold, color='#ff9900',
                                linestyle=':', linewidth=0.8, label='Drop threshold')
    ax_pos.set_xlim(0, window_s)
    ax_pos.set_ylim(-0.5, 26)
    ax_pos.set_ylabel('Position (mm)', color='#aaa')
    ax_pos.set_title('Continuous Lift Monitor', color='#ddd', pad=8)
    ax_pos.legend(fontsize=8, facecolor='#1a1a1a', labelcolor='#ccc', edgecolor='#333')

    live_val_text = ax_pos.text(
        0.02, 0.95, 'Live: — mm',
        transform=ax_pos.transAxes, fontsize=10, color='#4a9eff',
        va='top', fontfamily='monospace',
    )
    state_text = ax_pos.text(
        0.02, 0.85, 'State: ARMED',
        transform=ax_pos.transAxes, fontsize=9, color='#aaa',
        va='top', fontfamily='monospace',
    )
    lift_count_text = ax_pos.text(
        0.75, 0.95, 'Lifts: 0',
        transform=ax_pos.transAxes, fontsize=9, color='#4ade80',
        va='top', fontfamily='monospace',
    )

    # hz subplot
    (line_hz,) = ax_hz.plot([], [], color='#a78bfa', linewidth=1.2)
    ax_hz.set_xlim(0, window_s)
    ax_hz.set_ylim(0, 350)
    ax_hz.set_xlabel('Time (s)', color='#aaa')
    ax_hz.set_ylabel('Sampling rate (Hz)', color='#aaa')
    ax_hz.set_title('Live Sampling Frequency', color='#ddd', pad=8)

    # disconnection overlay
    _ov_kw = dict(ha='center', va='center', fontsize=11, color='#ff6b6b', visible=False,
                  bbox=dict(boxstyle='round,pad=0.6', facecolor='#111111',
                            edgecolor='#444', alpha=0.92))
    overlay_pos = ax_pos.text(0.5, 0.5, 'No linear sensor detected\nPlease plug in the USB',
                              transform=ax_pos.transAxes, **_ov_kw)

    # cooldown shading: keep list of (t_lift, patch) so old patches are removed
    _cooldown_patches: list = []

    _prev_connected = [True]
    _prev_lift_count = [0]

    def update(_frame):
        nonlocal window_s
        window_s = cfg.gui_window_size

        ts, ps, _ = bus.snapshot()
        connected = bus.is_connected

        if not ts:
            overlay_pos.set_visible(True)
            return (line_blue, line_green, line_hz, overlay_pos,
                    live_val_text, state_text, lift_count_text)

        if connected != _prev_connected[0]:
            _prev_connected[0] = connected
            fig.canvas.manager.set_window_title(
                'Continuous Lift Monitor' if connected
                else 'Continuous Lift Monitor — DISCONNECTED'
            )

        overlay_pos.set_visible(not connected)

        t_now  = ts[-1]
        cutoff = t_now - window_s

        start = 0
        for i, t in enumerate(ts):
            if t >= cutoff:
                start = i
                break

        ts_win = ts[start:]
        ps_win = ps[start:]

        ps_b_all, ps_g_all = _split_colors(
            ts, ps, cfg.lift_threshold, cfg.min_lift_duration
        )
        line_blue.set_data(ts_win,       ps_b_all[start:])
        line_green.set_data(ts_win,      ps_g_all[start:])
        ax_pos.set_xlim(t_now - window_s, t_now)
        hline.set_ydata([cfg.lift_threshold, cfg.lift_threshold])
        drop_hline.set_ydata([cfg.drop_threshold, cfg.drop_threshold])

        live_val_text.set_text(f'Live: {ps[-1]:.2f} mm')

        from .lift_detector import LiftState
        st = detector.state()
        color_map = {
            LiftState.ARMED:     '#aaaaaa',
            LiftState.PRE_LIFT:  '#f59e0b',
            LiftState.CONFIRMED: '#4ade80',
            LiftState.COOLDOWN:  '#f97316',
        }
        state_text.set_text(f'State: {st.name}')
        state_text.set_color(color_map.get(st, '#aaa'))

        lc = detector._lift_count
        if lc != _prev_lift_count[0]:
            _prev_lift_count[0] = lc
            lift_count_text.set_text(f'Lifts: {lc}')

            # Add a cooldown shading band starting at t_now
            cooldown = cfg.pellet_cooldown
            patch = ax_pos.axvspan(
                t_now, t_now + cooldown,
                alpha=0.12, color='#f97316', zorder=0
            )
            within_cd = detector.last_lift_time()
            _cooldown_patches.append((t_now + cooldown, patch))

        # Remove expired patches that are fully left of the window
        to_remove = [p for end_t, p in _cooldown_patches if end_t < t_now - window_s]
        for p in to_remove:
            p.remove()
        _cooldown_patches[:] = [(e, p) for e, p in _cooldown_patches
                                 if p not in to_remove]

        # Hz subplot
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
        ax_hz.set_xlim(t_now - window_s, t_now)

        return (line_blue, line_green, line_hz, overlay_pos,
                live_val_text, state_text, lift_count_text)

    _ani = animation.FuncAnimation(fig, update, interval=50, blit=False)

    def _on_close(_evt):
        stop_event.set()

    fig.canvas.mpl_connect('close_event', _on_close)
    plt.show()
