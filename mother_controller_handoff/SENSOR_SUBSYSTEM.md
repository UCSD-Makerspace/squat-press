# Sensor Subsystem — LX3302A inductive position sensor (INTEGRATED on the mother controller)

Measures lift height (0–~23 mm) of the squat platform. This is the **sole reward arbiter** in the product
(no rail in the field), so its integrity is critical.

Signal chain: **LX3302A → SENT (5 V) → BSS138 level shifter → GP15 (3.3 V) → RP2040 PIO decoder → USB → host**

---

## 1. Components

| Part | Detail |
|---|---|
| Sensor IC | **LX3302A** inductive position sensor, **chip ID 6880** (this specific unit is calibrated; see §4) |
| Target | The **white target piece that shipped with the sensor** (calibration is target-specific; aluminum needs its own cal) |
| Level shifter | **BSS138** 4-channel bidirectional (blue module on the bench). SENT is one channel, 5 V (HV) ↔ 3.3 V (LV) |
| MCU | **RP2040 / Raspberry Pi Pico**, running **bare MicroPython** (v1.28.0 known-good; v1.29.0 also works). No `main.py`. |

---

## 2. Pin map & wiring (CURRENT working topology)

**SENT input pin on the RP2040 = `GP15`.**

Power topology (this SUPERSEDED an earlier "kit powered by its own USB" scheme — the Pico now feeds the sensor):

| From | To | Purpose |
|---|---|---|
| Pico **VBUS (pin 40) = 5 V** | sensor **VIN** (kit J2 pin 2) **and** shifter **HV** | 5 V rail for sensor + shifter high side |
| Pico **3V3 (pin 36)** | shifter **LV** | 3.3 V reference for shifter low side |
| Pico **GND (pin 38)** | common ground: sensor **GND** (kit J2 pin 1) + shifter **GND** | single common ground |
| sensor **SENT** (kit J2 pin 4) | shifter **HV1 → LV1 → Pico GP15** | the SENT data line, level-shifted 5 V→3.3 V |

**Hard rules:**
- **Do NOT power sensor VIN from 3V3** (3.3 V is too low — this was the "sensor not getting power" bug).
- **Never put two 5 V sources on VIN** (if using Pico VBUS, do not also feed the kit's own USB 5 V).
- On a PCB you can drop the discrete BSS138 module for the equivalent circuit, but keep a real level
  translator — the SENT line idles high at 5 V and the RP2040 is 3.3 V (not 5 V tolerant).

---

## 3. SENT configuration (lives in the LX3302A EEPROM, set via Microchip IPCE 2.27.5)

Settled config (user: "this setting worked really well"):

- **REFRESH = 500 Hz**, **SENT CLK = 6 µs (`01`)**, **WDSCALE = 2**, **FILTER = SINC (`0`)**
- SENT interface: FCM = `0000` (Microchip-defined), SCM off, MSGMU disable, PPE disable
- **IO2 = `0101` = PP SENT** (IO1 = PP PWM, IO3 = DAC), all Safety_mode_on
- Misc: GADJ 3.125, CLSEL `1` (CL1=SIN, CL2=C), ADC10IN = Exciter, **ORIGIN = 2598**
- Clamps: **HCLMP = 3686**, **LCLMP = 409**

**⚠ For fast motion use 2 kHz / 3 µs / WDSCALE 1** instead — fast moves/falls at 500 Hz trip the **"1024 fault."**
The squat is fast, so the product will likely want the 2 kHz profile; validate against the 1024 fault.

**EEPROM discipline (critical):** a cal only persists if you click **"Program EEPROM to chip"** in IPCE.
Calibrating live without programming = garbage after the next power-cycle. Always Program → Read back, and
keep a **"Save EEPROM to file"** backup.

**Restore file:** `C:\Users\CMRG Lab\Documents\Induction_sensor\500hz.txt` (32-word IPCE dump). Load → Program to restore.
Full procedure: `C:\Users\CMRG Lab\Documents\Induction_sensor\SENSOR_CALIBRATION_PROTOCOL.md`.
*(These live on the PC, not in the repo — copies should be added to `firmware/` for the handoff.)*

---

## 4. Calibration (host side)

- Output-cal table (0–25 mm region cal, 2026-06-29, Max Error 0.195 %) is in the EEPROM: S0=1086/S7=1175,
  X1..X7 = 2815,3046,3213,3302,3391,3513,3745, Y1..Y7 = 1002,1547,1945,2136,2325,2569,3044.
- **Host mapping (`calibration.json`): `{"table": [[0, 3686], [22.86, 409]]}`** — SENT count **3686 → 0 mm**,
  **409 → 22.86 mm**, **linear and DECREASING with lift**. Full-scale ≈ 0–22.86 mm (~2.29 cm).
- Calibration is **target-specific** — changing the target (or material) requires a re-cal + re-program.

---

## 5. Timebase (important for any data logging on the mother controller)

- **The RP2040 is the master clock for the sensor.** Each SENT frame carries a hardware `device_t` timestamp.
- The host **batch-reads** (~6 frames every ~8.9 ms); do NOT timestamp with the host clock — that makes a
  staircase artifact. Use the Pico `device_t`.
- **Skew constant: `PICO_SKEW = 1.008295`** (`true_seconds = device_t × PICO_SKEW`). ⚠ **Per-Pico** — re-measure
  if the RP2040 is swapped (`measure_skew.py`). Streams ~680–816 Hz, CRC ~99 %.

---

## 6. Firmware notes (RP2040)

- **Bare MicroPython, no stored program.** The host pushes the SENT PIO decoder over the REPL on connect
  (`FWD_PROG` in `pico_pc.py` / the streamer `fwd.py`). A blank MicroPython Pico is a drop-in replica; the
  only per-unit config that matters is in the **LX3302A EEPROM**, not the Pico. **[verify on Pi]** exact files.
- **PIO memory leak — MANDATORY fix:** a MicroPython soft-reboot does NOT reset the RP2040 PIO. Repeated
  decoder pushes fill the 32-slot PIO instruction memory and the state machine **silently wedges (zero output,
  zero errors).** Always `rp2.PIO(0).remove_program()` **before** building the StateMachine.
- **Autonomous streaming is dead** — an on-flash `main.py` that streams before the host connects stalls the USB
  write (both v1.28 and v1.29). Do not revisit. The host must connect first, then arm.

---

## 7. Gotchas that will bite the PCB / integration

- **1024 fault on fast motion** at 500 Hz → use the 2 kHz SENT profile for the squat.
- **Vertical orientation drifts the sensor gap** → the mount must be **rigid, low-play**. Mechanical, but the
  board's mounting/connector choices affect it.
- **Keep every board off bare metal.** On the bench, a PCB resting on a metal surface shorted underside pads and
  produced *ever-changing* symptoms (power dropout, USB flapping, GP15 flipping state). On a real PCB: solid
  ground plane, no exposed pads that can short, proper standoffs/enclosure.
- **USB connector robustness matters.** The PCB sensor builds had the RP2040's **USB connector physically
  flapping** (dmesg `USB disconnect` bursts, port hopping ACM0↔ACM1) — a marginal connector/cable killed arming.
  Use a mechanically solid USB connector with strain relief; this was the #1 field-reliability problem.
- **Diagnose signal before firmware:** healthy GP15 ≈ 75–80 % high with thousands of transitions/s;
  `transitions=0 & hi_frac=1.000` = dead SENT (check 5 V/GND cable to sensor), not a code bug.
