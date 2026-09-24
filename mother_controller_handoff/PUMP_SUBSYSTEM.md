# Pump Subsystem — Peristaltic reward pump (SEPARATE PCB)

Delivers a small liquid reward (target 15 mg ≈ 15 µL of 1:1 Ensure/water) when the sensor confirms a
qualifying lift. **This is its own board** and carries the 24 V motor rail — the one part that can
electrically corrupt the sensor if grounds are shared (see `INTEGRATION_CONSTRAINTS.md`).

Drive chain: **RP2040 → TMC2209 SilentStepStick → ST42 2-channel 12-roller peristaltic head**

---

## 1. Components

| Part | Detail |
|---|---|
| MCU | **RP2040 / Raspberry Pi Pico**, runs **`pump.py`** on flash (a driver library; commanded over USB REPL) |
| Driver | **TMC2209 SilentStepStick** — **Watterott** module (TMC2209-LA, **0.11 Ω** sense resistors) |
| Motor / head | **ST42 2-channel, 12-roller** peristaltic pump, 200 steps/rev, rated **1.2 A/phase** |
| Motor rail | **24 V** (⚠ TMC2209 VM abs-max ~29 V — keep VMOT bulk cap ≥ 50 V rated) |
| Tube | 0.51 × 2.31 mm (0.90 mm wall). **Wall thickness (not ID) governs occlusion** — must stay ~0.9 mm or it siphons |

---

## 2. Pin map (rev3 board — the current working one)

| Signal | RP2040 pin | Notes |
|---|---|---|
| **STEP** | **GP17** | step pulses (PIO step train) |
| **DIR** | **GP16** | direction |
| **EN** (enable) | **GP26** | **active-low**; boots HIGH = disabled (safe); driver de-energizes between doses |
| **MS1** | **GP22** | with MS2 → microstep select; both LOW = 1/8 + UART node address 0 |
| **MS2** | **GP21** | " |
| **UART (PDN_UART)** | **GP19** | single-wire TMC2209 UART, 115200. Module **PDN_UART select-jumper bridged** center→UART/pin-5 pad (done 2026-09-01) |
| **(isolated PDN pad)** | **GP18** | **Hi-Z, NEVER drive** — driving it low clamps the shared UART bus. Leave as input, no pull. |

- **Microstep = 1/8** (MS1=MS2=LOW) → **1600 steps/rev** (200 × 8).
- On the Watterott module, the single chip PDN_UART pin is broken out to two jumper-selectable edge pads;
  the board ships with the select jumper **un-bridged** → neither pad reaches the chip. **You must bridge it
  to the GP19/UART side** (done on the bench). On a custom PCB, just route PDN_UART straight to GP19 and
  leave GP18 unused.

---

## 3. Motor current (VREF)

- Watterott TMC2209 sense = **0.11 Ω** → **I_RMS = 0.708 × VREF**.
- Bench setting: **VREF ≈ 1.17 V → 0.83 A RMS** (headroom below the ST42's 1.2 A rating; enough for the
  Ensure/water viscosity). Room to raise toward 1.2 A if it ever stalls; under-driving is otherwise safe.
- ⚠ Do NOT reuse the old HR4988 formula (`I = Vref/0.8`, 0.1 Ω) — this is a **different driver** now (TMC2209, 0.11 Ω).

---

## 4. Firmware (`pump.py`) — behavior & non-obvious constraints

- **Step generation:** PIO step train on **PIO0, SM0**.
- **TMC2209 config over single-wire UART** — brought up on **PIO1 (SM4/SM5)**. Sets StealthChop2, 256-microstep
  interpolation, and current registers: `GCONF=0x00000141`, `IHOLD_IRUN=0x00081F00` (IRUN=31), `TPOWERDOWN=0x14`,
  `TPWMTHRS=0`. Readback-verified (IOIN VERSION 0x21, IFCNT increments).
- **⚠ THE critical firmware rule — the UART must be TRANSIENT.** A *persistent* UART on PIO1 **silently stops
  the PIO0 step train.** So `pump.py` brings the UART up only to configure / soft-off, then **tears it down**
  (`rp2.PIO(1).remove_program()` + release GP19 to input) **before** stepping. Do not leave the UART running.
- **Silent soft-off** ramps `IHOLD_IRUN` down before `disable()` at the end of a dose — this **eliminated the
  end-of-dose "click"** (the TMC2209 snapping to a detent when current is cut abruptly).
- **PIO memory leak** (same as the sensor): `rp2.PIO(sm_id // 4).remove_program()` before building the SM, or the
  state machine wedges after a few restarts. Soft reboot does NOT clear it.
- **Dose = revolutions:** `dose_ul(uL)` → `revolutions(uL / uL_per_rev)`. So **dose mass ∝ 1 / uL_per_rev**.
- **Prime:** `prime_run(rpm)` (streaming, O(1) RAM) is the hold-to-run entry. The old table-preallocating
  `prime(seconds)` MemoryErrored on long primes — use the streaming version.
- **Not autonomous:** the Pico waits for REPL commands from the host (`pump_ctl.py`). It does not self-run.

---

## 5. Dose calibration (gravimetric, via the Mettler balance)

- **Current config:** `uL_per_rev = 12.60`, `dose_uL = 15.0` → 1.19 rev/dose.
- **Measured (2026-09-01, 216 s cadence):** ~**16.4 mg/dose, CV 1.2 %** — i.e. running **~1.4 mg high**.
  **To center on 15 mg: raise `uL_per_rev` 12.60 → ~13.82** (dose ∝ 1/uL_per_rev, so raise it to lower the dose).
- **⚠ Dose consistency is CADENCE- and TUBING-dependent (2026-09-02):** at **90 s** cadence the same config gave
  **CV 20.7 %** and a lower mean (14.6 mg), with a ~7-dose beat — the tube doesn't fully refill/rebound between
  fast doses (and/or air/roller-phase). **Volume is conserved over ~7 doses (CV falls to ~1.8 %).** Design
  implication: dosing cadence and tube routing/priming affect the delivered dose; calibrate at the cadence the
  study will actually use, and keep the outlet tube **rigidly fixed** (a moving tube tugs the weigh vessel / meters unevenly).
- First **~9 doses after priming are erratic** (air clearing) — prime out before counting a session.

---

## 6. Gotchas that will bite the PCB / integration

- **24 V→SENT coupling** — the pump's 24 V can conductively corrupt the sensor SENT through a **shared USB
  ground**. This is THE reason the pump is a separate board. See `INTEGRATION_CONSTRAINTS.md` §1. **Setup-dependent**
  (the v1 breadboard node did not couple; an older PCB build did) — but design as if it will.
- **USB inrush** — the pump Pico **cannot** share a loaded USB controller; plugging it into a busy Pi bus faulted
  the controller (`can't set config #1, error -62`) and took the rail down too. → **powered USB hub** (or isolation).
- **Never toggle 24 V while running** — the transient knocks the pump Pico (and any shared CP210x) off the USB bus
  and freezes the host. Sequence: 24 V up **before** launch, down **after**.
- **VMOT bulk cap ≥ 50 V rated** (100–220 µF low-ESR + 100 nF), but a huge cap worsens turn-on inrush — this is
  hygiene, not the coupling fix.
- **EN de-energizes between doses** → the compressed tube's elastic recovery can creep the rotor back (suck-back);
  roughly constant per stop, so it hurts small doses proportionally more.
