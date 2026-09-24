#!/usr/bin/env python3
"""
dose_weigh.py - gravimetric calibration of the reward pump, on the PC.

Watches the Mettler AM100 mass stream and automatically detects each dispensed dose as a
settled step in mass. Reports mean volume, SD, CV, and the implied uL/rev to type into the
Pi's pump GUI.

    python dose_weigh.py --port COM8 --density 1.06 --expected-ul 10 --ul-per-rev 60

Balance link (receive-only; see Downloads/files/CONTEXT.md for how this was won):
    COM8 Gearmo RS-422, 2400/7E1, balance in S.Cont + PAUSE .0.
    Needs BOTH the ~3 V receiver bias AND the inverted Rx polarity (pin 12 -> Rx-).
Parser and port setup are lifted from that project's mettler_stream_logger.py - do not
re-derive them here, they took real effort to get right.

HOW A DOSE IS DETECTED
    A window of the last W readings is "settled" when every reading is stable (not 'D')
    and the spread is <= --tol. The plateau is the window's median.
      * settled, and plateau differs from baseline by less than --min-step
            -> baseline FOLLOWS the plateau.
        This is what removes evaporation: the baseline creeps down with the drift, so a
        slowly evaporating vessel never accumulates into a phantom dose. The cost is that
        evaporation during the settle time itself (a few seconds) is still counted, which
        is negligible against a 10 mg dose.
      * settled, and plateau EXCEEDS baseline by >= --min-step
            -> that is a DOSE. A real dose lands in well under a second; the baseline
        cannot follow something that fast, which is exactly what separates the two cases.
      * settled, and plateau FALLS below baseline by >= --min-step
            -> mass was removed (spill, vessel touched). Flagged, not counted, re-baselined.

WHAT THE NUMBERS ARE WORTH
    CV is trustworthy even though the balance's calibration is ~35 years stale - a span
    error cancels in a ratio. ABSOLUTE volume is not: verify span with a known mass in the
    ~10 mg range before trusting uL/rev. Density matters too; Ensure is ~1.06 g/mL, so the
    "1 mg = 1 uL" water shortcut over-reads volume by ~6%.
"""

import argparse
import csv
import re
import statistics
import sys
import time
from collections import deque
from datetime import datetime

import serial

# "S     2.0110 g" / "SD    2.01 g". char 1 = ident, char 2 = status (D = dynamic).
_RESULT_RE = re.compile(
    r"^(?P<ident>[S\s])(?P<status>[\sD*])\s*(?P<value>-?[\d.]+)\s+(?P<unit>\S+)\s*$"
)
_TO_GRAMS = {"g": 1.0, "mg": 1e-3}


def open_port(port, baud=2400):
    return serial.Serial(port=port, baudrate=baud, bytesize=serial.SEVENBITS,
                         parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE,
                         timeout=0.2)


def parse(line):
    """line -> (grams, stable) or None if it is not a weight line."""
    m = _RESULT_RE.match(line)
    if not m:
        return None
    unit = m.group("unit")
    if unit not in _TO_GRAMS:
        return None
    return float(m.group("value")) * _TO_GRAMS[unit], m.group("status") != "D"


def lines(ser):
    """Yield decoded stream lines forever."""
    buf = bytearray()
    while True:
        b = ser.read(1)
        if not b:
            yield None                      # let the caller keep its display alive
            continue
        buf += b
        if buf.endswith(b"\r\n"):
            yield buf[:-2].decode("ascii", "replace")
            buf = bytearray()


def main():
    ap = argparse.ArgumentParser(description="Detect and weigh individual pump doses.")
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--density", type=float, default=1.0,
                    help="g/mL of the dosed liquid. water=1.00, Ensure~1.06 (default 1.0)")
    ap.add_argument("--expected-ul", type=float, default=None,
                    help="uL the pump was COMMANDED to deliver, for the uL/rev back-calc")
    ap.add_argument("--ul-per-rev", type=float, default=None,
                    help="uL/rev currently configured on the Pi, for the back-calc")
    ap.add_argument("--min-step", type=float, default=2.0,
                    help="mg; smallest jump counted as a dose (default 2.0)")
    ap.add_argument("--tol", type=float, default=0.4,
                    help="mg; max spread across the window to call it settled (default 0.4)")
    ap.add_argument("--window", type=int, default=10,
                    help="readings per settle window; ~6 Hz stream (default 10)")
    ap.add_argument("--out", default=None, help="CSV path (default dose_weigh_<stamp>.csv)")
    args = ap.parse_args()

    tol_g = args.tol * 1e-3
    min_step_g = args.min_step * 1e-3
    out_path = args.out or datetime.now().strftime("dose_weigh_%Y-%m-%d_%H%M%S.csv")

    ser = open_port(args.port)
    print("dose_weigh - %s @ 2400/7E1   density %.3f g/mL   min step %.1f mg   tol %.1f mg"
          % (args.port, args.density, args.min_step, args.tol))
    if args.density == 1.0:
        print("  NOTE: density 1.000 = water. For Ensure pass --density 1.06, "
              "or volumes read ~6% high.")
    print("  waiting for a settled baseline ... (Ctrl-C to finish and print stats)\n")

    win = deque(maxlen=args.window)
    baseline = None
    doses = []                  # grams
    t0 = time.monotonic()
    drift_g = 0.0               # signed baseline movement while NOT dosing
    quiet_s = 0.0
    last_quiet_t = None
    unsettled_since = None

    fh = open(out_path, "w", newline="")
    wr = csv.writer(fh)
    wr.writerow(["dose_index", "iso_time", "elapsed_s", "baseline_g", "plateau_g",
                 "delta_mg", "volume_ul", "note"])

    def record(note, plateau, delta_g):
        idx = len(doses)
        vol = delta_g * 1e3 / args.density          # g -> mL*1e3 = uL, / (g/mL)
        wr.writerow([idx if note == "dose" else "", datetime.now().isoformat(),
                     round(time.monotonic() - t0, 2), "%.5f" % baseline,
                     "%.5f" % plateau, "%.2f" % (delta_g * 1e3),
                     "%.2f" % vol if note == "dose" else "", note])
        fh.flush()
        return vol

    try:
        for line in lines(ser):
            if line is None:
                continue
            p = parse(line)
            if p is None:
                continue                       # SI / TA / start message - not a weight
            grams, stable = p
            win.append((grams, stable))

            now = time.monotonic()
            vals = [v for v, _ in win]
            settled = (len(win) == args.window and all(s for _, s in win)
                       and (max(vals) - min(vals)) <= tol_g)

            if not settled:
                unsettled_since = unsettled_since or now
                last_quiet_t = None
                sys.stdout.write("\r  %+9.4f g   (moving)      " % grams)
                sys.stdout.flush()
                continue

            plateau = statistics.median(vals)

            if baseline is None:
                baseline = plateau
                print("\r  baseline set at %+.4f g%s" % (baseline, " " * 12))
                last_quiet_t = now
                continue

            delta = plateau - baseline

            if delta >= min_step_g:
                vol = record("dose", plateau, delta)
                doses.append(delta)
                n = len(doses)
                mean_ul = statistics.mean(doses) * 1e3 / args.density
                sd_ul = statistics.stdev(doses) * 1e3 / args.density if n > 1 else 0.0
                cv = (sd_ul / mean_ul * 100.0) if n > 1 and mean_ul else 0.0
                print("\r  DOSE %-3d  %7.2f mg  =  %6.2f uL     "
                      "[n=%d  mean %.2f uL  SD %.2f  CV %.1f%%]"
                      % (n, delta * 1e3, vol, n, mean_ul, sd_ul, cv))
                baseline = plateau
                unsettled_since = None
                last_quiet_t = now
            elif delta <= -min_step_g:
                record("mass removed", plateau, delta)
                print("\r  ** mass DROPPED %.2f mg - spill or vessel disturbed. "
                      "Not counted; re-baselined.%s" % (-delta * 1e3, " " * 6))
                baseline = plateau
                last_quiet_t = now
            else:
                # Slow drift: let the baseline follow it, and account it as evaporation.
                if last_quiet_t is not None:
                    drift_g += delta
                    quiet_s += now - last_quiet_t
                last_quiet_t = now
                baseline = plateau
                sys.stdout.write("\r  %+9.4f g   settled       " % grams)
                sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        fh.close()

    n = len(doses)
    print("\n" + "-" * 68)
    if n == 0:
        print("No doses detected. If the pump did run, lower --min-step; if the reading "
              "never settled, raise --tol or check for vibration.")
        print("CSV: %s" % out_path)
        return

    ul = [d * 1e3 / args.density for d in doses]
    mean_ul = statistics.mean(ul)
    sd_ul = statistics.stdev(ul) if n > 1 else 0.0
    cv = (sd_ul / mean_ul * 100.0) if n > 1 and mean_ul else 0.0
    print("doses            : %d" % n)
    print("mean             : %.3f uL   (%.3f mg)" % (mean_ul, statistics.mean(doses) * 1e3))
    if n > 1:
        print("SD               : %.3f uL" % sd_ul)
        print("CV               : %.2f %%   <- the number that matters for a sub-roller dose"
              % cv)
        print("min / max        : %.2f / %.2f uL" % (min(ul), max(ul)))
    if quiet_s > 30:
        print("evaporation drift: %+.3f mg/min (removed from every dose by baseline tracking)"
              % (drift_g * 1e3 / (quiet_s / 60.0)))

    if args.expected_ul and args.ul_per_rev:
        revs = args.expected_ul / args.ul_per_rev
        true_upr = mean_ul / revs
        print("-" * 68)
        print("commanded        : %.2f uL  at  %.2f uL/rev  ->  %.4f rev per dose"
              % (args.expected_ul, args.ul_per_rev, revs))
        print("delivered        : %.3f uL  (%.1f%% of commanded)"
              % (mean_ul, mean_ul / args.expected_ul * 100.0))
        print("TRUE uL/rev      : %.2f      <- set this in the Pi pump GUI" % true_upr)
    print("-" * 68)
    print("CSV: %s" % out_path)
    print("Reminder: CV above is sound, but ABSOLUTE volume inherits the balance's ~35-year-old "
          "calibration.\nVerify span with a known mass near 10 mg before trusting uL/rev.")


if __name__ == "__main__":
    main()
