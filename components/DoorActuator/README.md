# DoorActuator arduino cycle test

Cycles a **Glideforce GF01-120503-1-66** micro linear actuator (12 V, 30 mm stroke,
2.2 kgf, 28 mm/s, 150 mA no-load / 400 mA max, built-in limit switches, 2 wires)
open/close N times at a slow speed — a stand-in for the mouse door.

Hardware: Arduino UNO R3 + **HW-130** motor shield (L293D "Adafruit Motor Shield v1" clone).

## Wiring

| From | To |
|---|---|
| actuator red / black | shield **M1** screw terminal (either order; swap if open/close are reversed) |
| 12 V DC supply (≥1 A) + / − | shield **EXT_PWR** terminal block **+** / **GND** |
| shield **PWR** jumper | **ON** — the 12 V also feeds the Uno's Vin, so it runs standalone (no USB) |
| Arduino USB | only needed to upload / watch the Serial Monitor; unplug for standalone use |

Shield stacks directly onto the UNO headers. Plug in the 12 V and the test starts by itself
(1.5 s grace, homes to retracted, then cycles). On-board LED **L**: on = running,
slow blink = done. Power-cycle or press RESET to run again.

## Software

1. Arduino IDE → *Tools → Manage Libraries* → install **"Adafruit Motor Shield library"** (the v1 one, provides `AFMotor.h`).
2. *Tools → Board → Arduino Uno*, pick the COM port.
3. Open `DoorActuator.ino`, upload, open Serial Monitor at **115200**.

Tunables at the top of the sketch: `N_CYCLES`, `SPEED` (PWM 0–255), `STROKE_MS`,
`DWELL_OPEN_MS` / `DWELL_CLOSED_MS`, and `PULSED` mode for motion slower than PWM allows.
Defaults = up → 3 s → down → 3 s, 100 times: 100 × (2 × 6 s + 2 × 3 s) = 30 min.

Re-flash from the PC (no IDE needed):
```
arduino-cli compile --fqbn arduino:avr:uno components/DoorActuator
arduino-cli upload  --fqbn arduino:avr:uno -p COM7 components/DoorActuator
```

## Notes

- The limit switches stop the motor at each end, so `STROKE_MS` just has to exceed the
  real travel time; while parked on a switch the actuator draws ~0 mA.
- The L293D drops ~2–3 V, so the actuator sees ~9–10 V (a bit slower than the datasheet).
- If it hums but doesn't move at low `SPEED`, raise it or set `PULSED = true`.
- If this actuator ends up on the live rig: mice hear 1–100 kHz, so PWM (any `SPEED` < 255)
  is likely audible to them. `SPEED = 255` is pure DC.
