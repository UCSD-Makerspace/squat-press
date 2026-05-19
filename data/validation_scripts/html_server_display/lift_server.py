"""
lift_server.py — standalone Flask dashboard demo
=================================================
Run this on its own (no GPIO, no serial) to understand the pattern before
wiring it into csv_log_only.py.

    pip install flask
    python lift_server.py

Then open http://localhost:5000 in a browser. The simulated lift loop at the
bottom updates the shared state every 3 seconds so you can watch the page
refresh live.

Pattern summary
───────────────
  _latest_lift   shared dict  — sensor loop writes, HTTP handler reads
  _state_lock    threading.Lock — every read and write goes through this
  update_latest_lift()  the one function csv_log_only.py will call
  start_server()        launches Flask in a daemon thread
"""

import threading
import time
from flask import Flask, jsonify, render_template_string

# ── Shared state ──────────────────────────────────────────────────────────────
# The sensor loop writes here; the HTTP handler reads here.
# RULE: always hold _state_lock when touching _latest_lift.

_state_lock  = threading.Lock()
_latest_lift = {}   # starts empty; first lift populates it

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Lift Dashboard</title>
  <style>
    body { font-family: monospace; max-width: 520px; margin: 60px auto; background: #0d0d0d; color: #e0e0e0; }
    h1   { font-size: 1.1rem; color: #aaa; letter-spacing: 0.12em; margin-bottom: 1.5rem; }
    table { width: 100%; border-collapse: collapse; }
    td   { padding: 10px 14px; border-bottom: 1px solid #222; }
    td:first-child { color: #777; width: 55%; }
    td:last-child  { color: #f0f0f0; font-size: 1.05rem; }
    #status { margin-top: 1rem; font-size: 0.75rem; color: #555; }
    .waiting { color: #555; font-style: italic; }
  </style>
</head>
<body>
  <h1>Linear Sensor Lift Dashboard</h1>
  <table id="tbl">
    <tr><td>Waiting for first lift...</td><td></td></tr>
  </table>
  <div id="status"></div>

  <script>
    const FIELDS = [
      ["Cycle",            "cycle"],
      ["Lift time",        "lift_time"],
      ["Gap from prev",    "gap_s",          v => v === null ? "N/A" : v.toFixed(2) + " s"],
      ["Peak height",      "peak_mm",        v => v.toFixed(2) + " mm"],
      ["Samples at peak",  "peak_samples",   v => v + " samples"],
      ["Peak duration",    "peak_dur_ms",    v => v.toFixed(1) + " ms"],
    ];

    async function poll() {
      try {
        const r = await fetch("/latest");
        const d = await r.json();
        if (Object.keys(d).length === 0) return;   // no lift yet

        const rows = FIELDS.map(([label, key, fmt]) => {
          const val = d[key] ?? "—";
          const display = (fmt && val !== "—") ? fmt(val) : val;
          return `<tr><td>${label}</td><td>${display}</td></tr>`;
        }).join("");
        document.getElementById("tbl").innerHTML = rows;
        document.getElementById("status").textContent =
          "Last updated " + new Date().toLocaleTimeString();
      } catch (e) {
        document.getElementById("status").textContent = "Fetch error: " + e;
      }
    }

    poll();
    setInterval(poll, 2000);   // re-fetch every 2 s
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

# ── Public API (called by csv_log_only.py) ────────────────────────────────────

def update_latest_lift(
    cycle:        int,
    lift_time:    str,
    gap_s:        float | None,
    peak_mm:      float,
    peak_samples: int,
    peak_dur_ms:  float,
):
    """Drop-in call at the end of each cycle in the sensor loop."""
    with _state_lock:
        _latest_lift.update({
            "cycle":        cycle,
            "lift_time":    lift_time,
            "gap_s":        gap_s,
            "peak_mm":      peak_mm,
            "peak_samples": peak_samples,
            "peak_dur_ms":  peak_dur_ms,
        })

def _tailscale_ip() -> str | None:
    """Return the Tailscale IPv4 address if Tailscale is running, else None."""
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
    """Launch Flask in a daemon thread. Returns immediately."""
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

# ── Simulated lift loop (remove this block when integrating into csv_log_only) ─

if __name__ == "__main__":
    import math

    start_server()

    prev_start = None
    cycle = 0

    print("Simulating a lift every 3 s. Open http://localhost:5000\n")

    while True:
        time.sleep(3)

        now       = time.time()
        gap_s     = round(now - prev_start, 2) if prev_start is not None else None
        prev_start = now
        cycle     += 1

        # fake values that vary each cycle so you can see the page update
        peak_mm      = round(19.0 + 0.4 * math.sin(cycle * 0.7), 2)
        peak_samples = 10 + (cycle % 6)
        peak_dur_ms  = round(45.0 + 8 * math.sin(cycle * 1.3), 1)

        update_latest_lift(
            cycle        = cycle,
            lift_time    = time.strftime("%H:%M:%S"),
            gap_s        = gap_s,
            peak_mm      = peak_mm,
            peak_samples = peak_samples,
            peak_dur_ms  = peak_dur_ms,
        )
        print(f"  lift {cycle:>3} | peak {peak_mm:.2f} mm | gap {gap_s}s")
