# Peristaltic Pump Reward (Liquid Dosing)

> **Compiled page.** Synthesised from
> [`sources/mother-controller/pump-subsystem.md`](sources/mother-controller/pump-subsystem.md),
> [`sources/mouse-reward-dosing.md`](sources/mouse-reward-dosing.md),
> [`sources/kamoer-pump-tubing.md`](sources/kamoer-pump-tubing.md).
> Regenerate if any source changes. **Related:** [mother-controller](mother-controller.md).

The current reward pump is a **Raspberry Pi Pico (RP2040) + TMC2209 SilentStepStick** driving an
**ST42 2-channel 12-roller** peristaltic head off a **24 V** motor rail. The sensor confirms a
qualifying lift; the host commands the pump Pico to deliver one metered dose.

> **Historical:** an earlier build used a **Kamoer stepper pump over Modbus/RS-485**. That design is
> **superseded** and its driver code was removed in the fall-2026 cleanup (recoverable from the
> `pre-cleanup` git tag). Its notes are retained as immutable sources
> ([kamoer-modbus-driver](sources/kamoer-modbus-driver.md),
> [kamoer-pump-tubing](sources/kamoer-pump-tubing.md)) for the tubing/dosing facts that still apply.

## Hardware & drive chain

`RP2040 → TMC2209 SilentStepStick (Watterott, 0.11 Ω sense) → ST42 12-roller head`, 24 V rail.

| Part | Notes |
|---|---|
| MCU | RP2040 / Pico, runs `pump.py` on flash, commanded over the USB REPL |
| Driver | TMC2209 SilentStepStick (Watterott, **0.11 Ω** sense resistors) |
| Motor / head | ST42 2-channel 12-roller, 200 steps/rev, rated 1.2 A/phase |
| Motor rail | **24 V** (TMC2209 VM abs-max ~29 V; VMOT bulk cap ≥ 50 V rated) |
| Tube | 0.51 × 2.31 mm (~0.9 mm wall) — **wall thickness, not ID, governs occlusion / anti-siphon** |

## Pin map (rev3 board)

| Signal | RP2040 pin | Notes |
|---|---|---|
| STEP | **GP17** | PIO step train |
| DIR | **GP16** | direction |
| EN | **GP26** | active-low; boots HIGH = disabled (safe); de-energizes between doses |
| MS1 / MS2 | **GP22 / GP21** | both LOW = 1/8 microstep = **1600 steps/rev** |
| UART (PDN_UART) | **GP19** | single-wire TMC2209 UART, 115200 |
| (isolated PDN pad) | **GP18** | **Hi-Z, never drive** (driving it clamps the shared UART bus) |

## Motor current

`I_RMS = 0.708 × VREF` (0.11 Ω board). Bench setting **VREF ≈ 1.17 V → 0.83 A RMS** (headroom below
the ST42's 1.2 A rating). **Do not** reuse the old HR4988 `I = VREF/0.8` (0.1 Ω) formula — different driver.

## Firmware (`pump.py`) — non-obvious rules

- Step train on **PIO0/SM0**; TMC2209 config over single-wire UART on **PIO1**.
- **The UART must be TRANSIENT** — a *persistent* UART on PIO1 silently stops the PIO0 step train.
  `pump.py` brings the UART up only to configure (StealthChop2, 256-µstep interp, current regs) and to
  soft-off, then tears it down before stepping.
- **Silent soft-off** ramps `IHOLD_IRUN` down before `disable()` → kills the end-of-dose "click."
- **PIO memory leak:** `rp2.PIO(n).remove_program()` before building each StateMachine (a soft reboot
  does not clear PIO), or the SM wedges after a few restarts.
- `dose_ul()` → revolutions, so **dose mass ∝ 1 / `uL_per_rev`**. Not autonomous — waits for host commands.

## Dose calibration (gravimetric, via the Mettler balance)

- Current config: **`uL_per_rev = 12.60`, `dose_uL = 15.0`** → 1.19 rev/dose.
- Measured (216 s cadence): ~16.4 mg/dose, CV 1.2 % (running ~1.4 mg high). **To center on 15 mg:
  raise `uL_per_rev` 12.60 → ~13.82.**
- **Dose consistency is cadence- and tubing-dependent:** at 90 s cadence the same config gave CV 20.7 %
  with a ~7-dose beat (tube doesn't fully refill between fast doses); volume is conserved over ~7 doses.
  **Calibrate at the study's actual cadence, and keep the outlet tube rigidly fixed.** The first ~9 doses
  after priming are erratic (air) — prime out before counting.

## Code

In-repo at [`components/PeristalticPump/`](../components/PeristalticPump/): `pump.py` (Pico firmware)
and `pump_ctl.py` (Pi-side host driver; auto-detects the pump by finding `pump.py` on the Pico's flash).
In normal operation the pump is driven by the rig's dosing app, not by hand.
