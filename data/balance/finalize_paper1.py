#!/usr/bin/env python3
"""Finalize the Paper_1 session: render Paper_1.png + write Paper_1_summary.txt from Paper_1.csv.
Self-contained -- reads only the local balance CSV, never touches the Pi. Safe to run any time.
   python finalize_paper1.py [density]     (default density 1.03 for 1:1 Ensure/water)
"""
import sys, csv, statistics, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dose_detect import DoseDetector

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "Paper_1.csv")
D = float(sys.argv[1]) if len(sys.argv) > 1 else 1.03

t = []; m = []; st = []
for r in csv.DictReader(open(CSV)):
    t.append(float(r["elapsed_s"])); m.append(float(r["mass"])); st.append(r["stable"] == "True")

det = DoseDetector(density=D); ds = []; downs = []
for ti, mi, si in zip(t, m, st):
    ev = det.push(ti, mi, si)
    if ev and ev[0] == "dose": ds.append((ti, ev[2] * 1e3))
    elif ev and ev[0] == "removed": downs.append((ti, ev[2] * 1e3))

# clean doses = plausible single doses (drop bumps / re-tares)
clean = [(ti, d) for ti, d in ds if 5 < d < 40]
v = [d for _, d in clean]

lines = []
def out(s): lines.append(s); print(s)

out("=== Paper_1 session - %.2f h, %d readings ===" % (t[-1] / 3600, len(m)))
out("doses detected: %d   (clean 5-40 mg: %d)   down-events: %d" % (len(ds), len(clean), len(downs)))
if v:
    mean = statistics.mean(v); sd = statistics.stdev(v) if len(v) > 1 else 0
    out("clean dose: mean %.2f mg = %.2f uL   SD %.2f   CV %.1f%%   range %.1f-%.1f mg"
        % (mean, mean / D, sd, sd / mean * 100 if mean else 0, min(v), max(v)))
    out("total delivered (clean): %.1f mg = %.3f mL of mix" % (sum(v), sum(v) / D / 1000))
    # hourly drift
    out("--- per-hour (clean doses):")
    hrs = int(t[-1] // 3600) + 1
    for h in range(hrs):
        seg = [d for ti, d in clean if h * 3600 <= ti < (h + 1) * 3600]
        if seg:
            out("  h%d: n=%2d  mean %.2f mg = %.2f uL  CV %.0f%%"
                % (h + 1, len(seg), statistics.mean(seg), statistics.mean(seg) / D,
                   statistics.stdev(seg) / statistics.mean(seg) * 100 if len(seg) > 1 else 0))
    # detect an air/dry breakdown: first hour where CV jumps > 25%
    for h in range(hrs):
        seg = [d for ti, d in clean if h * 3600 <= ti < (h + 1) * 3600]
        if len(seg) > 3 and statistics.stdev(seg) / statistics.mean(seg) * 100 > 25:
            out("  ** hour %d CV>25%% -> likely reservoir low / air (check the trace there)" % (h + 1))
            break

# ---- figure
fig, ax = plt.subplots(figsize=(13, 5.5))
mm = [x * 1e3 for x in m]
ax.plot([x / 3600 for x in t], mm, lw=0.9, color="#2b7")
for ti, d in ds:
    ax.axvline(ti / 3600, color="#bbb", lw=0.3, alpha=0.3)
ax.set_xlabel("time (h)"); ax.set_ylabel("mass (mg)"); ax.grid(True, alpha=0.3)
title = "Paper_1 session - %.2f h" % (t[-1] / 3600)
if v:
    title += "   |   %d doses, mean %.2f uL, CV %.1f%%, total %.2f mL" % (
        len(clean), statistics.mean(v) / D,
        statistics.stdev(v) / statistics.mean(v) * 100 if len(v) > 1 else 0, sum(v) / D / 1000)
ax.set_title(title, fontsize=11)
fig.tight_layout()
png = os.path.join(HERE, "Paper_1.png"); fig.savefig(png, dpi=130)
open(os.path.join(HERE, "Paper_1_summary.txt"), "w").write("\n".join(lines) + "\n")
out("saved: Paper_1.png  +  Paper_1_summary.txt")
