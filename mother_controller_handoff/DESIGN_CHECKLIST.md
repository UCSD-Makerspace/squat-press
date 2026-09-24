# Mother Controller — Design Checklist (hard rules for the layout)

A punch list distilled from the working bench rig. Each item is a rule that, if broken, caused a real failure.

## Power & grounding
- [ ] **Isolate the pump's 24 V domain from the sensor SENT ground** (USB isolator on the pump link, e.g. ADuM4160 + isolated 24 V→5 V DC-DC, FS strap). *[Integration §1, §6]*
- [ ] Sensor 5 V (Pico VBUS) feeds **both** the LX3302A VIN and the level-shifter HV; 3V3 feeds shifter LV; single common ground. *[Sensor §2]*
- [ ] **Never** power sensor VIN from 3V3, and **never** two 5 V sources on VIN. *[Sensor §2]*
- [ ] VMOT bulk cap **≥ 50 V** rated (100–220 µF low-ESR + 100 nF) near the TMC2209; mind turn-on inrush. *[Pump §6]*
- [ ] 24 V rail gated so it **cannot be toggled mid-session**; expose clean up-before-start / down-after-stop sequencing. *[Integration §3]*
- [ ] Solid ground plane; **no exposed shortable pads**; the timing-critical SENT ground kept away from motor return currents. *[Integration §4, §6]*

## USB
- [ ] Pump USB goes through a **powered hub / isolated powered port** — never a shared, loaded host controller. *[Integration §2]*
- [ ] **Mechanically solid, strain-relieved USB connectors** (board-integrated preferred). USB connector flapping was the #1 reliability failure. *[Sensor §7, Integration §4]*
- [ ] If both Picos are on one host, give each a **stable USB serial number / VID:PID**, or preserve content-based detection (pump = has `pump.py`, sensor = bare). *[Integration §5]*

## Sensor
- [ ] SENT (5 V) → level translator → **GP15** (RP2040 is 3.3 V, NOT 5 V tolerant). *[Sensor §2]*
- [ ] Provide access to the LX3302A for **IPCE programming** (the EEPROM cal must be *Programmed to chip*, not live-only). *[Sensor §3]*
- [ ] Plan for the **2 kHz SENT profile** for fast squats (500 Hz trips the 1024 fault on fast motion). *[Sensor §3, §7]*
- [ ] Rigid, low-play sensor mount (vertical orientation drifts the gap). *[Sensor §7]*

## Pump
- [ ] TMC2209 pinout: STEP=GP17, DIR=GP16, EN=GP26 (active-low), MS1=GP22, MS2=GP21, **PDN_UART→GP19**, **GP18 left Hi-Z (never drive).** *[Pump §2]*
- [ ] MS1=MS2 low = 1/8 microstep (1600 steps/rev). *[Pump §2]*
- [ ] Set motor current for the **TMC2209 / 0.11 Ω** board: I_RMS = 0.708 × VREF (bench ≈ 1.17 V → 0.83 A). Do **not** reuse the old HR4988 0.1 Ω formula. *[Pump §3]*
- [ ] Route PDN_UART directly to GP19 (no jumper needed on a custom board); keep the single-wire UART **transient** in firmware. *[Pump §2, §4]*
- [ ] Outlet tube **rigidly fixed** and wall thickness ~0.9 mm (wall, not ID, governs occlusion / anti-siphon). *[Pump §1, §5]*

## Firmware carry-over (whatever the host is)
- [ ] `rp2.PIO(n).remove_program()` **before** every StateMachine build (PIO memory leak) — both Picos. *[Sensor §6, Pump §4]*
- [ ] Pump UART is **transient only** (persistent UART on PIO1 stops the PIO0 step train). *[Pump §4]*
- [ ] Host pushes the SENT decoder to the sensor Pico over REPL; **no autonomous main.py** (it wedges USB). *[Sensor §6]*
- [ ] Serial handles opened with a **write_timeout** (a blocking write on a re-enumerated device freezes the host). *[from app hardening]*

## Calibration state to carry forward
- [ ] Sensor EEPROM = chip **6880** config (or re-cal per unit); host `calibration.json` = `[[0,3686],[22.86,409]]`, target-specific. *[Sensor §3, §4]*
- [ ] Pump: `uL_per_rev` **12.60 → ~13.82** to hit 15 mg; **re-calibrate gravimetrically at the study's actual dosing cadence** (dose is cadence/tube dependent). *[Pump §5]*
