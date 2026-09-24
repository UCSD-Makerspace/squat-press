# Mother controller — integrated sensor + separate pump board

*Compiled from: [system-overview](sources/mother-controller/system-overview.md),
[sensor-subsystem](sources/mother-controller/sensor-subsystem.md),
[pump-subsystem](sources/mother-controller/pump-subsystem.md),
[integration-constraints](sources/mother-controller/integration-constraints.md),
[design-checklist](sources/mother-controller/design-checklist.md),
[sensor-calibration-protocol](sources/mother-controller/sensor-calibration-protocol.md).
Related: [topology](topology.md), [peristaltic-pump](peristaltic-pump.md).*

Constraints + context for laying out the **mother controller** PCB, distilled from the working
bench rig. The spec bundle (a deliverable pointer) lives at
[`docs/mother-controller-spec/`](../docs/mother-controller-spec/); the firmware to carry forward
lives with the code in [`components/PeristalticPump/`](../components/PeristalticPump/) and
[`components/LinearSensor/pico_viewer/`](../components/LinearSensor/pico_viewer/).

## Scope

| Subsystem | On the mother controller? |
|---|---|
| **Induction position sensor** (LX3302A + BSS138 level shifter + RP2040/SENT) | **YES — integrated** |
| **Peristaltic reward pump** (RP2040 + TMC2209 + 24 V) | **NO — its own separate PCB** (the 24 V board) |
| **Linear rail** (AZD-KD, RS-485) | Excluded — bench-only squat replay |
| **Weighing scale** (Mettler AM100) | Excluded — pump calibration instrument only |

**Architectural fact:** both Picos run **bare MicroPython**. The host pushes the SENT decoder to the
sensor Pico over the USB REPL at runtime, and commands the pump Pico (`pump.py` on flash) over its
REPL. Autonomous on-Pico streaming was tried and **permanently abandoned** (it wedges the USB write).
**The host is the brain and is not optional.**

**First decision:** carry the Raspberry Pi 5 as the host (option A — all existing software works
unchanged, lowest risk) vs. an onboard MCU (option B — a real firmware port). Recommended: **A**.

## The electrical must-reads (these cost the most bench time)

1. **24 V → SENT coupling is why the pump is a separate board.** With 24 V on, decoded SENT collapsed
   to CRC 0 %; with 24 V off it was clean (~700 fps, CRC 100 %). Proven **conducted through the shared
   USB ground** (unplugging the pump Pico's USB fixed it with 24 V still on). SENT is fragile because
   all its data is in falling-edge timing (±3 µs). **Fix: a USB isolator on the pump link** (ADuM4160
   + isolated 24 V→5 V DC-DC, Full-Speed strap) — "keep data, break ground." Setup-dependent (a clean
   breadboard node didn't couple; an older PCB build did) → **design as if it will, and re-test CRC with
   24 V on.**
2. **USB inrush:** the pump Pico cannot share a loaded USB controller (it faulted the bus, `error -62`,
   and took the rail's CP210x down). Route it through a **powered hub / isolated powered port**.
3. **24 V sequencing:** never toggle 24 V while running (transient knocks devices off USB, freezes the
   host). Up **before** launch, down **after** stop; gate it so it can't switch mid-session.
4. **Grounding/shorts:** solid ground plane, no exposed shortable pads, keep the timing-critical SENT
   ground out of the 24 V motor return. Intermittent, character-changing power/USB/signal faults = suspect
   a physical short first.
5. **USB connector robustness** was the #1 field-reliability problem (a flapping connector killed arming)
   — use mechanically solid, strain-relieved, board-integrated USB.
6. **Device identity:** USB port names shuffle → resolve by content (pump = has `pump.py`, sensor = bare),
   or give each Pico a stable serial number / VID:PID.

## Sensor subsystem (integrated)

- Chain: **LX3302A (chip 6880) → SENT 5 V → BSS138 → GP15 (3.3 V) → RP2040 PIO decoder → USB → host.**
- Power: Pico **VBUS 5 V** feeds sensor VIN **and** shifter HV; **3V3** feeds shifter LV; single common
  ground. Never power VIN from 3V3; never two 5 V sources on VIN. RP2040 is **not** 5 V tolerant → keep a
  real level translator.
- SENT config lives in the **LX3302A EEPROM** (set via Microchip IPCE, must be *Programmed to chip*):
  bench profile 500 Hz / 6 µs / WDSCALE 2, clamps HCLMP 3686 / LCLMP 409. **Use the 2 kHz / 3 µs profile
  for fast squats** (500 Hz trips the 1024 fault on fast motion).
- Host calibration `calibration.json` = `[[0, 3686], [22.86, 409]]` (count → mm, decreasing, ~0–22.86 mm),
  target-specific. Timebase: RP2040 `device_t` is master; `PICO_SKEW = 1.008295` (per-Pico, re-measure if swapped).

## Pump subsystem (separate PCB)

- Chain: **RP2040 → TMC2209 SilentStepStick (Watterott, 0.11 Ω) → ST42 12-roller head**, 24 V motor rail.
- Pin map (rev3): **STEP=GP17, DIR=GP16, EN=GP26 (active-low), MS1=GP22, MS2=GP21, PDN_UART→GP19,
  GP18 Hi-Z (never drive).** MS1=MS2 low = 1/8 microstep (1600 steps/rev). On a custom PCB route PDN_UART
  straight to GP19 (no jumper).
- Current: **I_RMS = 0.708 × VREF** (0.11 Ω board), bench ≈ 1.17 V → 0.83 A. Do **not** reuse the old
  HR4988 0.1 Ω formula.
- Firmware rule: the single-wire UART must be **transient** — a persistent UART on PIO1 silently stops the
  PIO0 step train. `pump.py` brings the UART up only to configure / soft-off, then tears it down before
  stepping. Silent soft-off (ramp `IHOLD_IRUN` down before disable) kills the end-of-dose click.
- Dose: `dose_ul()` → revolutions, so dose ∝ 1/`uL_per_rev`. Current `uL_per_rev = 12.60`, `dose_uL = 15.0`;
  raise `uL_per_rev` → ~13.82 to center on 15 mg. **Dose consistency is cadence- and tubing-dependent** —
  calibrate gravimetrically at the study's real cadence; keep the outlet tube rigidly fixed.

## Design checklist

The layout punch list (power/grounding, USB, sensor, pump, firmware carry-over, calibration state) is kept
verbatim as an immutable source: [design-checklist](sources/mother-controller/design-checklist.md).

## Open decisions

1. Host = carry the Pi (A) vs. onboard MCU (B).
2. SENT rate: 500 Hz vs 2 kHz profile (2 kHz for fast squats).
3. Pump isolation: USB isolator (recommended) vs. digital isolator on STEP/DIR/EN.
4. Dose recalibration `uL_per_rev` 12.60 → ~13.82 and re-cal at the real cadence.
