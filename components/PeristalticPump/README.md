# PeristalticPump

Liquid-reward dosing via a **Kamoer stepper peristaltic pump** on a **MODBUS-RTU
(RS-485)** driver. Full documentation: [`wiki/peristaltic-pump.md`](../../wiki/peristaltic-pump.md).

## Files

- **`pump_calibrator_gui.py`** — Tkinter GUI to configure, calibrate, and drive the
  pump: every driver register + coil, a dose helper (µL ↔ revolutions), single-step
  and timed-dose controls, live status, and a paced confirmed-stop. The serial port
  auto-defaults to `COM8` (Windows) / `/dev/ttyUSB0` (Pi).
- **`pump_diag.py`** — read-only register dump (sends no motor commands).
  `python pump_diag.py [port]`.

## Run

```bash
pip install pymodbus pyserial        # tkinter ships with Python
python pump_calibrator_gui.py        # PC: COM8   ·   Pi: set port to /dev/ttyUSB0
```

## Dose model

One **Single-step** press = one dose = `circles ÷ pitch` revolutions
(saved default `75 ÷ 100` = **0.75 rev ≈ 44 µL**). Driver config, DIP settings,
tubing, control coils, and the gravimetric calibration procedure are in the wiki page.
