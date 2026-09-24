# Mother Controller — Handoff Package

Constraints + context for designing the **mother controller** board for the squat-press mouse
resistance-training rig. Built from the working bench rig (a Raspberry Pi 5 driving three USB devices).

**Start with `SYSTEM_OVERVIEW.md`, then read `INTEGRATION_CONSTRAINTS.md` before any layout.**

---

## ⚠ READ FIRST — the repo is partly STALE vs. the current bench rig

This package documents the **current working rig** (what you're building toward). Some committed files in
the repo are from **earlier hardware generations** and will mislead you if taken at face value:

| Thing | Repo has (committed) | Current rig / this handoff | Use |
|---|---|---|---|
| **Pump** | **Kamoer stepper over Modbus/RS-485** (`components/PeristalticPump/`, COM8 9600 8N1, DIP current, 59 µL/rev) | **Pico + TMC2209 SilentStepStick, single-wire UART** (`firmware/pump.py`) | **Use the TMC2209 design.** The Kamoer Modbus pump is superseded — ignore for the mother controller. |
| **Sensor decode** | Two paths: (a) `pico_viewer/` PIO-SENT on **GP15** ✅, (b) older ASCII `F/G/A` serial driver (`serial_reader.py`, 26-pt table) | PIO-SENT on **GP15** (`pico_viewer/`) | **Use the `pico_viewer` PIO-SENT path.** The ASCII driver is the old eval-board approach. |
| **Other TMC2209 files** | `tests/.../timer_lifts.ino` (ESP32), `components/TMC2209/tmc2209.py` (pins DIR=5/STEP=19…) | — | **NOT the pump.** These drive the sensor-test lift actuator and the pellet dispenser — different pins, different board. Don't cross-wire. |
| **Rail / scale** | rail not in repo; Balance (scale) untracked | excluded from product | Out of scope. |
| **Schematic / KiCad / gerber / BOM** | **none exist** | — | You're starting the PCB from scratch; no prior layout to inherit. |

The sensor `calibration.json` in the repo (`[[0,3686],[22.86,409]]`) **does** match the current rig — validated.

---

## Documents

| File | What it covers |
|---|---|
| **`SYSTEM_OVERVIEW.md`** | Architecture, scope (in/out), block diagram, the host (Pi vs onboard MCU) decision. |
| **`SENSOR_SUBSYSTEM.md`** | LX3302A + BSS138 + RP2040/SENT: pins, power topology, EEPROM config, calibration, timebase, firmware, gotchas. |
| **`PUMP_SUBSYSTEM.md`** | RP2040 + TMC2209 + ST42: pin map, motor current, microstep, UART, dose calibration, firmware, gotchas. |
| **`INTEGRATION_CONSTRAINTS.md`** | **The electrical must-reads** — 24 V→SENT isolation, USB inrush, grounding, power sequencing, device identity. |
| **`DESIGN_CHECKLIST.md`** | A punch list of hard rules to satisfy on the layout. |

## `firmware/` — the actual code & config to carry forward

| File | Source | Role |
|---|---|---|
| `pump.py` | working copy (deployed to the pump Pico) | **Current** TMC2209 pump driver (PIO steps, transient UART, StealthChop2, silent soft-off, `dose_ul`). |
| `pump_ctl.py` | working copy (Pi host) | Host-side pump control over USB REPL (`find_pump_port`, `dose`, `prime_*`, `write_timeout=2`). |
| `sensor_decoder__pico_pc.py` | repo `pico_viewer/` | **Current** sensor decoder — host pushes the PIO SENT decoder, decodes framed binary; the authoritative sensor firmware. |
| `sensor_decoder__pico_live.py` | repo `pico_viewer/` | Lighter console variant of the same decoder. |
| `sensor_calibration.json` | PC `Documents\Induction_sensor` | Host count→mm table `[[0,3686],[22.86,409]]`. |
| `sensor_eeprom_500hz.txt` | PC `Documents\Induction_sensor` | LX3302A EEPROM dump (chip 6880) — IPCE "Load EEPROM from file" → "Program EEPROM to chip" to restore. |
| `SENSOR_CALIBRATION_PROTOCOL.md` | PC `Documents\Induction_sensor` | Step-by-step sensor cal procedure. |
| `SENSOR_pico_viewer_README.md` | repo `pico_viewer/` | Sensor viewer docs (RP2040 PIO edge-timing, host decode, Pi deploy). |
| `deploy_view.sh` | repo `pico_viewer/` | Pi launch helper for the sensor viewer. |
| `host_app_reference__endurance_pump.py` | working copy (Pi host) | **Reference only** — the combined sensor+pump(+rail) app. Shows the lift-trigger dose rule, arming, hotplug handling. (Contains rail code = out of scope; read for integration patterns.) |

---

## Still on the Pi / not captured here (retrieve when the Pi is back on)

- The exact on-Pi sensor **arm** path (`_arm_sensor`/`start_pico`/`FWD_PROG`) as currently deployed — `pico_pc.py` here carries the decoder, but confirm against the live Pi copy.
- `pico_clock.py` (holds `PICO_SKEW = 1.008295` + time helpers) — value is documented in `SENSOR_SUBSYSTEM.md §5`.
- Any Pi-side `run_pump_app.sh` launcher specifics.

## Open decisions for you to make (flagged in the docs)

1. **Host = carry the Pi, or an onboard MCU?** (`SYSTEM_OVERVIEW.md`) — carrying the Pi keeps all software unchanged.
2. **SENT rate** — 500 Hz vs 2 kHz profile (fast squats trip the 1024 fault at 500 Hz). (`SENSOR_SUBSYSTEM.md §3`)
3. **Pump isolation method** — USB isolator (recommended) vs digital isolator on STEP/DIR/EN. (`INTEGRATION_CONSTRAINTS.md §1`)
4. **Dose recalibration** — `uL_per_rev` 12.60 → ~13.82 for 15 mg, and re-cal at the study's real cadence (dose is cadence/tube dependent). (`PUMP_SUBSYSTEM.md §5`)
