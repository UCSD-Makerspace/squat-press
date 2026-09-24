# Squat-Press

Automated mouse **squat-press** resistance-training rig. A mouse performs a squat/press against a
platform; a linear **inductive position sensor** (LX3302A) measures lift height, and when a lift
qualifies, a **peristaltic pump** delivers a small liquid reward. A bench-only linear rail replays
recorded squats for characterisation; a balance is used to calibrate the pump gravimetrically.

> **Documentation lives in the [`wiki/`](wiki/)**, structured with the Karpathy LLM-wiki method
> (compiled pages derived from immutable `sources/`). Start with
> **[wiki/topology.md](wiki/topology.md)** for how the rig is wired, powered, and started.

## Current architecture

The host is a **Raspberry Pi 5** (`192.168.137.50`) driving three USB devices. Ports are resolved
**by content, never by fixed port** (they shuffle across reboots):

| Role | Hardware | Identified by |
|---|---|---|
| **Sensor** | LX3302A → SENT → BSS138 → RP2040 (PIO edge-timing) → host decode | bare Pico (no `pump.py`) |
| **Pump** | RP2040 + TMC2209 SilentStepStick → ST42 12-roller head, 24 V | Pico whose flash carries `pump.py` |
| **Rail** *(bench only)* | Oriental Motor AZD-KD, RS-485/Modbus | CP210x / `ttyUSB0` |

Both Picos run **bare MicroPython**: the host pushes the SENT decoder to the sensor Pico over the USB
REPL at runtime, and commands the pump Pico's `pump.py` over its REPL. See
[wiki/topology.md](wiki/topology.md) and [wiki/peristaltic-pump.md](wiki/peristaltic-pump.md).

## Repository layout

```
squat-press/
├── components/         # Hardware drivers (code only)
│   ├── LinearSensor/
│   │   └── pico_viewer/     # CURRENT sensor path: PIO-SENT decode + lift/velocity dashboard
│   ├── PeristalticPump/     # CURRENT pump: pump.py (Pico+TMC2209) + pump_ctl.py (Pi host driver)
│   ├── PhotoInterruptor/    # beam-break detection
│   ├── StepperMotor/        # stepper .ino
│   ├── TMC2209/             # low-level TMC2209 register helper (NOT the pump board)
│   └── DoorActuator/        # mouse-door cycle tester (.ino)
├── data/               # Research datasets + analysis (code that operates on data)
│   ├── csv/                 # logged CSVs by YYYY.MM.DD/
│   ├── balance/             # gravimetric pump-calibration runs + analysis scripts
│   └── validation_scripts/
├── docs/               # Deliverables / specs (not live code)
│   └── mother-controller-spec/   # pointer to the wiki spec + shippable-bundle notes
├── wiki/               # Documentation source of truth (compiled pages + immutable sources/)
└── tests/              # Scaffold (old suite cleared in the fall-2026 cleanup)
```

## Running the rig

The live dosing app runs **on the Pi's desktop**, launched hands-off:

- **Start Rig** desktop icon → `~/induction/rig_start.sh` (auto-detects the three devices, arms the
  sensor, opens the GUI).
- **Stop Rig** desktop icon → `~/induction/rig_stop.sh` (stops the app, frees the ports).
- **The one hard rule:** never toggle 24 V while the app is running (see [wiki/topology.md](wiki/topology.md)).

## Notes

- **The production dosing app (`endurance_pump.py`) currently lives only on the Pi**, not in this repo.
  Mirroring it here is a known follow-up.
- History before the fall-2026 cleanup (old USB-serial sensor driver, `run_core/`, Kamoer Modbus pump,
  Pi-4/pigpio scripts) is recoverable from the **`pre-cleanup`** git tag.
