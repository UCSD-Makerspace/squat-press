# PeristalticPump

Liquid-reward dosing via a **Raspberry Pi Pico (RP2040) + TMC2209 SilentStepStick**
driving a peristaltic pump. The Pico runs a PIO step train (jerk-limited S-curve) with a
*transient* single-wire TMC2209 UART for StealthChop2, current tuning, and a silent
soft-off. Full design notes and the gravimetric calibration procedure live in the wiki:
[`wiki/peristaltic-pump.md`](../../wiki/peristaltic-pump.md).

## Files

- **`pump.py`** — firmware that runs *on the pump Pico*. Pins: `STEP=GP17 DIR=GP16 EN=GP26
  MS1=GP22 MS2=GP21`, UART on `GP19` (GP18 isolated — never drive). Exposes `dose_ul()`.
- **`pump_ctl.py`** — Pi-side host driver. Auto-detects the pump by finding `pump.py` on the
  Pico's flash (never by port number — the ACM ports shuffle on reboot). Calibrated defaults:
  `DEFAULT_DOSE_UL = 15.0`, `UL_PER_REV = 12.60`.

## Deploy / run

`pump.py` is flashed to the pump Pico (see the deploy helper on the Pi in `~/induction/`).
In normal operation the pump is driven by the rig's dosing app, not by hand.

> The older **Kamoer Modbus/RS-485** pump driver was removed in the fall-2026 cleanup
> (recoverable from the `pre-cleanup` git tag). This TMC2209 design supersedes it.
