# Mother Controller — System Overview & Scope

**Purpose of this package:** constraints + context for designing the "mother controller" board for the
squat-press mouse resistance-training rig. It consolidates everything learned building the working
bench rig so the PCB can be laid out without re-discovering the hard-won electrical and firmware gotchas.

> Status of the source rig: fully working on the bench as three USB devices driven by a Raspberry Pi 5.
> The mother controller re-packages that into hardware. All facts here are from the working rig; anything
> that lives only on the (currently powered-off) Pi/Picos is flagged **[verify on Pi]**.

---

## What the mother controller carries vs. what it doesn't

| Subsystem | On the mother controller? | Notes |
|---|---|---|
| **Induction position sensor** (LX3302A + level shifter + RP2040/SENT) | **YES — integrated** | The sensor PCB folds into the mother controller. See `SENSOR_SUBSYSTEM.md`. |
| **Peristaltic reward pump** (RP2040 + TMC2209 + 24 V) | **NO — its own separate PCB** | Interfaces to the mother controller over USB. **This is the electrically dangerous one** (24 V). See `PUMP_SUBSYSTEM.md` + `INTEGRATION_CONSTRAINTS.md`. |
| **Linear rail** (Oriental Motor AZD-KD, RS-485/Modbus) | **NO — excluded** | Bench-only actuator that replays recorded squats; a real mouse has no rail. Not part of the product. |
| **Weighing scale** (Mettler AM100, RS-422) | **NO — excluded** | Calibration instrument only, used to gravimetrically calibrate the pump. Not part of the product. |

The rail and scale are **out of scope** for the mother controller. They are named only where they explain
why something is the way it is (e.g., the sensor is the *sole* reward arbiter because the animal has no rail).

---

## Block diagram (current bench architecture)

```
                       ┌─────────────────────────────────────────────┐
                       │            HOST  (Raspberry Pi 5)            │
                       │  - pushes SENT decoder to sensor Pico (REPL) │
                       │  - runs the dosing app (endurance_pump.py)   │
                       │  - drives pump Pico over USB REPL            │
                       └───────────────┬───────────────┬─────────────┘
                                       │ USB           │ USB (via powered hub / isolator)
              ┌────────────────────────▼──┐         ┌──▼─────────────────────────────┐
              │  SENSOR NODE  (on mother   │         │  PUMP PCB  (separate board)     │
              │  controller)               │         │                                 │
              │  RP2040 (bare MicroPython) │         │  RP2040 (pump.py on flash)      │
              │   GP15 ← SENT              │         │   → TMC2209 SilentStepStick     │
              │  BSS138 level shifter 5→3V3│         │      STEP/DIR/EN/MS1/MS2 + UART │
              │  LX3302A sensor (chip 6880)│         │   → ST42 12-roller pump head    │
              │  target = matched white pc │         │   24 V motor rail  ⚠ ISOLATE    │
              └────────────────────────────┘         └─────────────────────────────────┘
```

**Key architectural fact:** both Picos run **bare MicroPython**; the sensor decoder is *pushed at runtime
over the USB REPL* by the host, and the pump firmware (`pump.py`) lives on the pump Pico's flash and is
*commanded* over the USB REPL. Neither Pico runs autonomously (autonomous auto-stream was tried and
**permanently abandoned** — it wedges the USB write). **The host is not optional** — it is the brain.

---

## The one host decision you must make first

The bench "brain" is a Raspberry Pi 5. The mother controller can either:

- **(A) Carry the Pi** (Pi as a compute module / plugged-in SBC; the board is a carrier + sensor + connectors).
  → All existing host-side software (`pico_pc.py` decoder push, `endurance_pump.py`, `pump_ctl.py`) works unchanged. **Lowest risk.**
- **(B) Replace the Pi with an onboard MCU.** → You must re-implement the host roles: push/stream the SENT
  PIO decoder to the sensor Pico, and command the pump Pico. This is a real firmware port. Higher risk.

**Recommendation: (A)** unless there's a compelling size/cost reason. Everything in this package assumes the
host roles are preserved, however they're physically provided.

---

## Files in this package

- `SYSTEM_OVERVIEW.md` — this file.
- `SENSOR_SUBSYSTEM.md` — LX3302A + BSS138 + RP2040/SENT: pins, power, EEPROM config, calibration, firmware, gotchas.
- `PUMP_SUBSYSTEM.md` — RP2040 + TMC2209 + ST42: pins, current, microstep, UART, dose calibration, firmware, gotchas.
- `INTEGRATION_CONSTRAINTS.md` — **the electrical must-reads**: 24 V→SENT isolation, USB inrush, grounding, power sequencing.
- `DESIGN_CHECKLIST.md` — a punch list of hard rules to satisfy on the layout.
- `firmware/` — the actual firmware + config files to hand to the mother controller's software.
