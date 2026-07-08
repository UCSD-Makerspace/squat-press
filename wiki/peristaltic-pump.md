# Peristaltic Pump Reward (Liquid Dosing)

> **Compiled page.** Synthesised from
> [`sources/kamoer-modbus-driver.md`](sources/kamoer-modbus-driver.md),
> [`sources/kamoer-pump-tubing.md`](sources/kamoer-pump-tubing.md),
> [`sources/mouse-reward-dosing.md`](sources/mouse-reward-dosing.md).
> Regenerate if any source changes.

A Kamoer stepper peristaltic pump dispenses a precise water reward over Modbus
RTU (RS-485). One **single-step trigger = one metered dose**.

## Hardware & wiring

| Part | Notes |
|---|---|
| Kamoer KPMP10 (KPM10-ST-A2) pump | 24 V stepper, 0–5.9 mL/min, 4-roller head |
| Kamoer MODBUS-RTU driver (10.10.0013) | max 32 microsteps; current DIP-set |
| Gearmo GM-482422 USB↔RS-485 | PC `COM8`, Pi `/dev/ttyUSB*` |
| 24 V bench supply | ~1–2 A |

- RS-485 **`B G A`** 3-pin port: Gearmo pin1→A, pin2→B, pin5→G (swap 1↔2 if silent).
- Motor `A+ A- B+ B-`; power `V+ V-`. The 6-pin block is motor+power, **not** comms.

## DIP (RS-485 mode)
SW1–5 OFF · SW6 ON · SW7-9 = OFF/OFF/OFF (**subdivision 32**) · SW10-12 = ON/OFF/ON (**1 A**).
Power-cycle after any DIP change. **The subdivision register must match SW7-9.**

## Comms
`9600 8N1`, addr `1`. 32-bit params = 2 registers low-word-first. Pace frames
≥ 70 ms and retry per-op (comms is flaky while the motor spins).

## Saved dosing config (flash, 2026-07-08)
| Register | Value |
|---|---|
| Subdivision `0x0001` | 32 |
| Step angle `0x0000` | 180 |
| Start freq `0x0002` | 50 Hz (anti-jerk) |
| Accel/decel `0x0003` | 300 Hz |
| Pitch `0x0004-5` | 100 |
| Stop mode `0x0007` | 0 (slow) |
| Speed `0x0008` | 30 rpm (set at run time) |
| Circles `0x0009-0A` | 75 → **0.75 rev/dose** |
| Direction `0x000B` | 0 (fwd) |

`revolutions = circles ÷ pitch = 75 ÷ 100 = 0.75 rev`.

## Dosing one reward
1. Ensure enabled (`0x004F`=0), set speed (`0x0008`, non-zero), set circles (`0x0009-0A`).
2. **Pulse** coil `0x0007` ON→OFF → runs exactly `circles/pitch` rev once, self-stops.
3. Confirmed stop (safety): coils `0x0004/0x0005/0x0007` OFF + speed 0, then read `0x0030` until 0.

## Dose target
~44 µL/dose ≈ 8 µL/lift (150 lifts/day, 5–6 lifts/dose, ~1.2 mL/day). Saved
0.75 rev is the nominal dose. **Calibrate gravimetrically** (weigh ~20 doses,
1 mg = 1 µL) to convert 0.75 rev → exact µL, then fine-tune `circles`.

## Tubing
Head takes 1.52 × 3.22 mm (= 1/16"×1/8"). In use: **PharMed BPT 1/16"×1/8"**
(USP Class VI). Marginal fit → verify no free-siphon at rest (anti-siphon loop)
and re-calibrate after any tube change.

## Calibration GUI
`pump_calibrator_gui.py` (Tkinter): exposes every register/coil, a dose helper
(µL ↔ revolutions), single-step + timed-dose, and a paced confirmed-stop.
Connect at `COM8 / 9600 / addr 1` (PC) or set port `/dev/ttyUSB*` (Pi).
*(To be added to the repo under `components/PeristalticPump/`.)*
