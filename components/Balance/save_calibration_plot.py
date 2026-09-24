#!/usr/bin/env python3
"""Render + archive a dosing run as a figure with dose annotations and stats.
   usage: python save_calibration_plot.py mass_run26.csv "2026-07-22 15uL tube-decoupled"
"""
import sys, csv, shutil, statistics
import matplotlib
matplotlib.use("Agg")                       # headless render, no display needed
import matplotlib.pyplot as plt
from dose_detect import DoseDetector

src = sys.argv[1] if len(sys.argv) > 1 else "mass_run26.csv"
label = sys.argv[2] if len(sys.argv) > 2 else "dosing run"
stem = "calibration_" + src.replace("mass_run", "run").replace(".csv", "")

t = []; m = []; st = []
for r in csv.DictReader(open(src)):
    t.append(float(r["elapsed_s"])); m.append(float(r["mass"])); st.append(r["stable"] == "True")

# detect doses; clip the one bump-artifact spike so it doesn't wreck the axes
det = DoseDetector(density=1.0); ds = []
for ti, mi, si in zip(t, m, st):
    ev = det.push(ti, mi, si)
    if ev and ev[0] == "dose" and abs(ev[2]) < 1.0:      # <1 g = a real dose, not a pan bump
        ds.append((ti, ev[2] * 1e3))

ss = [d for ti, d in ds if ti > 150]                     # steady-state (line primed)
mean = statistics.mean(ss); sd = statistics.stdev(ss); cv = sd / mean * 100
upr = 96.0 * mean / 15.0                                 # interim config was 96 uL/rev, 15 uL cmd

fig, ax = plt.subplots(figsize=(12, 5.5))
mm = [mi * 1e3 for mi in m]
ax.plot(t, mm, lw=1.0, color="#2b7", label="mass on balance")
for ti, d in ds:
    ax.axvline(ti, color="#888", lw=0.4, alpha=0.4)
ax.set_xlabel("time (s)"); ax.set_ylabel("mass (mg)")
ax.set_ylim(-50, max(mm) * 1.05 if mm else 100)
ax.grid(True, alpha=0.3)
ax.set_title("Reward-pump dosing — %s\n"
             "steady-state (t>150 s): n=%d   mean %.2f mg   SD %.2f   CV %.1f%%   -> true ~%.0f uL/rev"
             % (label, len(ss), mean, sd, cv, upr), fontsize=11)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
fig.savefig(stem + ".png", dpi=130)
shutil.copy(src, stem + ".csv")

print("saved: %s.png" % stem)
print("saved: %s.csv  (copy of %s)" % (stem, src))
print("steady-state n=%d  mean %.2f mg  SD %.2f  CV %.1f%%  true uL/rev ~%.0f"
      % (len(ss), mean, sd, cv, upr))
