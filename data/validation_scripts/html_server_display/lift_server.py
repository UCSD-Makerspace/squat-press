"""
lift_server.py — Flask dashboard for live lift data
====================================================
Imported by periodic_lift_tracker.py. Call start_server() once at startup,
then update_latest_lift() after every cycle to push new data to the dashboard.

Standalone demo (no hardware):
    python lift_server.py
"""

import threading
import time
from flask import Flask, jsonify, render_template_string

_state_lock  = threading.Lock()
_latest_lift = {}

app = Flask(__name__)

_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Lift Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
      background: #0d0d0d; color: #f0f0f0;
      max-width: 780px; margin: 0 auto; padding: 40px 24px 80px;
    }
    h1 { font-size: 0.85rem; color: #999; letter-spacing: 0.18em;
         text-transform: uppercase; margin-bottom: 28px; }
    h2 { font-size: 0.75rem; color: #999; letter-spacing: 0.14em;
         text-transform: uppercase; margin: 36px 0 12px; }

    /* ── Metadata table ── */
    table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    td { padding: 10px 0; border-bottom: 1px solid #2a2a2a; vertical-align: top; }
    td:first-child { width: 52%; padding-right: 16px; }
    .label   { color: #c0c0c0; font-size: 0.9rem; }
    .sublabel{ color: #6a6a6a; font-size: 0.72rem; margin-top: 3px; line-height: 1.35; }
    .value   { color: #ffffff; font-size: 1.05rem; }

    /* ── Graphs ── */
    .graph-wrap { position: relative; margin-top: 4px; }
    .graph-wrap img { width: 100%; border-radius: 4px; display: block; }
    .graph-wrap img.hidden { display: none; }
    .dl-btn {
      display: inline-block; margin-top: 8px;
      font-size: 0.72rem; color: #888; text-decoration: none;
      border: 1px solid #3a3a3a; border-radius: 3px;
      padding: 3px 10px; transition: color 0.15s, border-color 0.15s;
    }
    .dl-btn:hover { color: #ddd; border-color: #777; }

    /* ── Hz stats ── */
    #hz-stats {
      margin-top: 14px; padding: 14px 16px;
      background: #111; border: 1px solid #2a2a2a; border-radius: 4px;
      font-size: 0.82rem; color: #b8b8b8; line-height: 1.9;
    }
    #hz-stats .hl { color: #d4c5ff; }

    /* ── Error explanation ── */
    #hz-explain {
      margin-top: 12px; padding: 14px 16px;
      background: #0f0f0f; border: 1px solid #2a2a2a; border-radius: 4px;
      font-size: 0.79rem; color: #909090; line-height: 1.8;
    }
    #hz-explain strong { color: #c0c0c0; display: block; margin-bottom: 6px; }
    #hz-explain .formula {
      margin: 10px 0; padding: 8px 12px;
      background: #1a1a1a; border-radius: 3px;
      color: #c4b5fd; letter-spacing: 0.03em;
    }
    #hz-explain .note { color: #666; margin-top: 8px; font-size: 0.74rem; }

    /* ── Status bar ── */
    #status { margin-top: 32px; font-size: 0.7rem; color: #555; }
    .waiting { color: #555; font-style: italic; }
  </style>
</head>
<body>
  <h1>Linear Sensor Live Lift Dashboard</h1>

  <table id="tbl">
    <tr><td colspan="2" class="waiting">Waiting for first lift&hellip;</td></tr>
  </table>

  <h2>Latest Lift Trace</h2>
  <div class="graph-wrap">
    <img id="lift-img" class="hidden" alt="Lift trace">
    <br>
    <a id="lift-dl" class="dl-btn" href="#" download="lift.png">Download PNG</a>
  </div>

  <h2>Sampling Frequency Distribution</h2>
  <div class="graph-wrap">
    <img id="hz-img" class="hidden" alt="Hz distribution">
    <br>
    <a id="hz-dl" class="dl-btn" href="#" download="hz_distribution.png">Download PNG</a>
  </div>
  <div id="hz-stats">Waiting for first lift&hellip;</div>

  <div id="hz-explain">
    <strong>How is the worst-case position error calculated?</strong>
    The sensor samples at ~200 Hz, but not at perfectly even intervals — the gap
    between consecutive samples varies slightly. This variation is called
    <em>timing jitter</em>, measured as the standard deviation of all inter-sample
    intervals within the cycle.
    <br><br>
    If the sensor is moving at velocity <em>v</em> (mm/s) and timing is uncertain
    by &sigma;<sub>t</sub> seconds, the position reading could be off by:
    <div class="formula">
      &plusmn; position error &nbsp;=&nbsp; max_velocity (mm/s) &nbsp;&times;&nbsp; &sigma;<sub>t</sub> (s)
    </div>
    We use the <em>maximum</em> observed velocity (not the average) because that
    is the hardest case — it occurs during the fast acceleration phase of the lift
    (~85 mm/s), not at the slow dwell near the peak. This is a conservative 1&sigma;
    bound: ~68% of samples fall within this error, ~95% within 2&times; this value.
    <div class="note">
      Example: at 85 mm/s with 1 ms timing std &rarr; &plusmn;0.085 mm worst-case.
      Near the peak (&lt;12 mm/s) the same jitter gives &lt;&plusmn;0.012 mm.
    </div>
  </div>

  <div id="status"></div>

  <script>
    function formatGap(v) {
      if (v === null || v === undefined) return "N/A — first lift";
      const total = Math.round(v * 10) / 10;
      if (total >= 60) {
        const mins = Math.floor(total / 60);
        const secs = (total % 60).toFixed(1);
        return `${mins} minute${mins !== 1 ? 's' : ''} ${secs} seconds`;
      }
      return total.toFixed(2) + " seconds";
    }

    function formatMs(ms) {
      return ms === null ? "—" : ms.toFixed(1) + " milliseconds";
    }

    const FIELDS = [
      {
        label: "Cycle",
        key:   "cycle",
        fmt:   v => "#" + v,
      },
      {
        label: "Lift time",
        key:   "lift_time",
      },
      {
        label:    "Time since previous lift",
        key:      "gap_s",
        fmt:      v => formatGap(v),
      },
      {
        label:    "Length of lift",
        sublabel: "Time from first to last recorded sample in this cycle",
        key:      "lift_duration_s",
        fmt:      v => (v * 1000).toFixed(1) + " milliseconds",
      },
      {
        label:    "Peak height detected",
        key:      "peak_mm",
        fmt:      v => v.toFixed(2) + " mm",
      },
      {
        label:    "Samples above detection threshold",
        sublabel: "Number of data points recorded while position ≥ 19.0 mm",
        key:      "peak_samples",
        fmt:      v => v + " data points",
      },
      {
        label:    "Duration above detection threshold",
        sublabel: "Time from the first sample crossing 19.0 mm to the last sample above 19.0 mm",
        key:      "peak_dur_ms",
        fmt:      v => formatMs(v),
      },
    ];

    function setGraph(imgId, dlId, dlName, b64) {
      if (!b64) return;
      const src = "data:image/png;base64," + b64;
      const img = document.getElementById(imgId);
      img.src = src;
      img.classList.remove("hidden");
      const dl = document.getElementById(dlId);
      dl.href = src;
      dl.download = dlName;
    }

    async function poll() {
      try {
        const r = await fetch("/latest");
        const d = await r.json();
        if (!d || Object.keys(d).length === 0) return;

        const rows = FIELDS.map(({label, sublabel, key, fmt}) => {
          const raw = d[key];
          const display = (raw === null || raw === undefined)
            ? "—"
            : (fmt ? fmt(raw) : raw);
          const sub = sublabel
            ? `<div class="sublabel">${sublabel}</div>`
            : "";
          return `<tr>
            <td><div class="label">${label}</div>${sub}</td>
            <td><div class="value">${display}</div></td>
          </tr>`;
        }).join("");
        document.getElementById("tbl").innerHTML = rows;

        setGraph("lift-img", "lift-dl", `lift_cycle_${d.cycle}.png`, d.graph_b64);
        setGraph("hz-img",  "hz-dl",  `hz_cycle_${d.cycle}.png`,   d.hz_graph_b64);

        if (d.hz_mean !== undefined) {
          document.getElementById("hz-stats").innerHTML =
            `Cycle ${d.cycle} &nbsp;|&nbsp; `+
            `Mean <span class="hl">${d.hz_mean} Hz</span> &nbsp;&plusmn;&nbsp; `+
            `<span class="hl">${d.hz_std} Hz</span> (1&sigma;)<br>`+
            `Maximum observed velocity: <span class="hl">${d.max_vel_mm_s} mm/s</span><br>`+
            `Worst-case position error from timing jitter (1&sigma;): `+
            `<span class="hl">&plusmn;${d.mm_error_1sig} mm</span>`;
        }

        document.getElementById("status").textContent =
          "Last updated " + new Date().toLocaleTimeString();
      } catch (e) {
        document.getElementById("status").textContent = "Fetch error: " + e;
      }
    }

    poll();
    setInterval(poll, 2000);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(_HTML)

@app.route("/latest")
def latest():
    with _state_lock:
        return jsonify(dict(_latest_lift))

# ── Public API ────────────────────────────────────────────────────────────────

def update_latest_lift(
    cycle:          int,
    lift_time:      str,
    gap_s:          float | None,
    peak_mm:        float,
    peak_samples:   int,
    peak_dur_ms:    float,
    lift_duration_s:float,
    hz_mean:        float,
    hz_std:         float,
    mm_error_1sig:  float,
    max_vel_mm_s:   float,
    graph_b64:      str | None,
    hz_graph_b64:   str | None,
):
    with _state_lock:
        _latest_lift.update({
            "cycle":           cycle,
            "lift_time":       lift_time,
            "gap_s":           gap_s,
            "peak_mm":         peak_mm,
            "peak_samples":    peak_samples,
            "peak_dur_ms":     peak_dur_ms,
            "lift_duration_s": lift_duration_s,
            "hz_mean":         hz_mean,
            "hz_std":          hz_std,
            "mm_error_1sig":   mm_error_1sig,
            "max_vel_mm_s":    max_vel_mm_s,
            "graph_b64":       graph_b64,
            "hz_graph_b64":    hz_graph_b64,
        })

def _tailscale_ip() -> str | None:
    import subprocess
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def start_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, use_reloader=False, threaded=True),
        daemon=True,
    )
    t.start()
    ts_ip = _tailscale_ip()
    if ts_ip:
        print(f"Dashboard → http://{ts_ip}:{port}  (Tailscale — share this URL)")
    else:
        print(f"Dashboard → http://localhost:{port}  (Tailscale not detected — LAN only)")

# ── Standalone demo ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import math

    start_server()
    prev_start = None
    cycle = 0
    print("Simulating a lift every 3 s. Open http://localhost:5000\n")

    while True:
        time.sleep(3)
        now        = time.time()
        gap_s      = round(now - prev_start, 2) if prev_start is not None else None
        prev_start = now
        cycle     += 1

        update_latest_lift(
            cycle           = cycle,
            lift_time       = time.strftime("%H:%M:%S"),
            gap_s           = gap_s,
            peak_mm         = round(19.0 + 0.4 * math.sin(cycle * 0.7), 2),
            peak_samples    = 10 + (cycle % 6),
            peak_dur_ms     = round(45.0 + 8 * math.sin(cycle * 1.3), 1),
            lift_duration_s = round(0.62 + 0.02 * math.sin(cycle * 0.4), 3),
            hz_mean         = round(215.0 + 5 * math.sin(cycle * 0.9), 1),
            hz_std          = round(8.5 + 1.5 * math.sin(cycle * 1.1), 1),
            mm_error_1sig   = round(0.004 + 0.001 * math.sin(cycle), 4),
            max_vel_mm_s    = round(85.0 + 3 * math.sin(cycle * 0.6), 1),
            graph_b64       = None,
            hz_graph_b64    = None,
        )
        print(f"  lift {cycle:>3} | peak {19.0 + 0.4 * math.sin(cycle * 0.7):.2f} mm")
