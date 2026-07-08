# Squat-Press

Repository for the automated mice squat-press system. The rig measures a mouse performing a squat/press motion using a linear inductive position sensor, dispenses a food pellet reward via a stepper motor, and optionally streams lift data to a live web dashboard.

---

## Repository Structure

```
squat-press/
├── components/              # Shared hardware drivers (used by run_core and scripts)
│   ├── LinearSensor/        # LX3302A driver, calibration table, interpolation
│   ├── PhotoInterruptor/    # Beam-break pellet detection
│   ├── StepperMotor/        # TMC2209 stepper motor driver
│   └── TMC2209/             # Low-level TMC2209 register interface
│
├── run_core/                # Main integrated system entry point
│   ├── threads/             # Hardware threads (sensor, dispenser, plotter, LTC)
│   ├── event_manager.py     # Orchestrates cross-thread events
│   ├── events.py            # EventType enum (LIFT_DETECTED, PELLET_DISPENSED, …)
│   ├── main.py              # Entry point — run this on the Pi
│   └── utils.py             # Hardware init helpers
│
├── data/
│   ├── csv/                 # Logged CSV data, sorted by YYYY.MM.DD/
│   └── validation_scripts/
│       ├── html_server_display/
│       │   ├── lift_server.py          # Flask server for online lift display
│       │   └── periodic_lift_tracker.py  # Core Pi script: GPIO sync + CSV + web dashboard
│       └── live_graph_pos.py           # Laptop-side live scrolling position graph
│
└── tests/
    ├── component_unit_tests/
    │   ├── dispenser_motor_pcb_test/   # Flash to PCB Pico (pellet dispenser motor)
    │   ├── mice_door/                  # Flash to linear actuator controller (mice door)
    │   └── pd_unit_test/               # Legacy pellet dispenser unit test
    └── linear_sensor/
        ├── calibration/                # Calibration data collection scripts
        ├── mice_step_fn_mimic/         # Flash to ESP32 for linear sensor unit test
        ├── timer_lifts/                # Flash to ESP32 for periodic automated lifts
        ├── csv_log_only.py             # GPIO-synced uncapped CSV logger (Pi)
        ├── LXK_monitoring.py           # Live terminal readout of sensor values
        └── LXK_live_vals.py            # High-speed raw sampling rate test
```

---

## Hardware

| Component | Part | Notes |
|---|---|---|
| SBC | Raspberry Pi 4 | Pi 5 not supported (pigpio incompatibility) |
| Position sensor | LX3302AL012 50 mm Linear Inductive | Reads via USB-serial at 115200 baud |
| Stepper motor | TMC2209-driven | Pellet dispenser |
| Sync microcontroller | ESP32 | Sends GPIO HIGH/LOW to Pi to mark lift start/end |
| Pellet dispenser MCU | Raspberry Pi Pico (on PCB) | Runs `dispenser_motor_pcb_test.ino` |
| Mice door actuator | Arduino-compatible | Runs `mice_door.ino` |

### Linear Sensor Wiring (Pi ↔ LX3302A)

| Pi | LX3302A |
|---|---|
| Ground | Ground |
| 5 V | +5 V supply |
| GPIO 18 (pin 12) | IO 2 (SENT) |

### ESP32 Sync Wiring

| ESP32 | Pi |
|---|---|
| GPIO 5 (RPI_SYNC_PIN) | GPIO 21 (BCM) |
| GND | GND |

---

## Peristaltic Pump Reward (Liquid Dosing)

Optional liquid-reward path: a **Kamoer stepper peristaltic pump** dispenses a metered water dose over **Modbus RTU (RS-485)** — one single-step trigger ≈ one **~44 µL** dose.

Full documentation lives in the wiki, structured with the **Karpathy LLM-wiki method** (a compiled page derived from immutable sources): **[`wiki/peristaltic-pump.md`](wiki/peristaltic-pump.md)** — hardware, DIP/register config, dosing math, tubing, and the calibration GUI.

---

## Software Components

### `components/LinearSensor/`

Centralised driver for the LX3302A sensor. All scripts that read the sensor import from here — do not copy-paste the calibration table or interpolation function into other files.

- **`CALIBRATION_TABLE`** — 26-point lookup table (0–25 mm, calibrated 2026-06-04) mapping raw ADC integers to millimetres
- **`interpolate(raw)`** — linearly interpolates the table; returns `None` if out of range
- **`LinearSensorReader`** — serial connection class with connect/disconnect helpers

```python
from components.LinearSensor import interpolate, LinearSensorReader
```

### `run_core/main.py` — Integrated System

Runs the full experiment loop on the Pi. Starts four concurrent threads:

| Thread | Purpose |
|---|---|
| `LinearSensorThread` | Polls sensor, fires `LIFT_DETECTED` / `LIFT_COMPLETED` events |
| `LTCThread` | Listens for pellet-taken confirmation |
| `DispenserThread` | Activates stepper motor to dispense a pellet |
| `PlotThread` | Maintains a rolling position plot |

`EventManager` consumes the shared event queue and coordinates reward delivery.

**To run:**
```bash
cd /path/to/squat-press
python run_core/main.py
```

### `data/validation_scripts/html_server_display/periodic_lift_tracker.py` — Web Dashboard (Pi)

Runs on the Pi. Polls the sensor at full speed, detects lift cycles via GPIO sync from the ESP32 (with a software rolling-average fallback), logs per-sample CSVs, and pushes lift summaries to a local Flask server (`lift_server.py`) that serves a live web dashboard.

- GPIO pin BCM 21 from the ESP32: HIGH = cycle start, LOW = cycle end
- Software fallback threshold: rolling average of 10 samples crossing 0.175 mm
- Peak threshold: 19.0 mm
- CSV saved to `data/csv/YYYY.MM.DD/gpio_sensorN_HHMMSS.csv`

**To run on Pi:**
```bash
python data/validation_scripts/html_server_display/periodic_lift_tracker.py
```

### `data/validation_scripts/live_graph_pos.py` — Live Graph (Laptop)

Plug the sensor directly into the lab laptop via USB. Displays a scrolling 10-second position graph plus a live sampling-rate (Hz) graph. No Pi or network required.

**Features:**
- Scrolling 10-second position window and live Hz graph
- Line turns **green** when a lift is valid (above threshold for ≥ minimum lift duration); stays **blue** otherwise
- Configurable lift threshold (set at startup) and minimum lift duration (editable live in the UI)
- **Start / Stop CSV recording** — records all samples with timestamps; on Stop, prompts for a save location and shows session stats (lift count, average Hz, mean samples above threshold)
- **Hot-swap support** — unplug and replug the sensor at any time; graph shows a reconnecting overlay and resumes automatically
- Live position readout at top of window (current mm + 0.1-second rolling average)

**To run:**
```bash
# Auto-detect port (will prompt if multiple found)
python data/validation_scripts/live_graph_pos.py

# Specify port explicitly
python data/validation_scripts/live_graph_pos.py COM3          # Windows
python data/validation_scripts/live_graph_pos.py /dev/ttyACM0  # Linux / Pi
```

**Keyboard shortcuts:** `S` = Start recording, `E` = Stop recording

---

## Firmware (Arduino / ESP32)

### `tests/linear_sensor/timer_lifts/timer_lifts.ino` — Periodic Automated Lifts (ESP32)

Flash to the ESP32 connected to the TMC2209 stepper driver. Performs one lift every hour (configurable), pulses GPIO 5 HIGH at lift start and LOW at lift end to sync with the Pi. Used together with `periodic_lift_tracker.py` to run overnight automated experiments.

Motion profile mirrors a real mouse lift (step-function velocity segments derived from 120fps video analysis, peaking at ~19.5 mm).

**Flash target:** ESP32 (TMC2209 on Serial2, RX=16, TX=17, ENABLE=19)

### `tests/component_unit_tests/dispenser_motor_pcb_test/dispenser_motor_pcb_test.ino`

Flash to the Raspberry Pi Pico on the pellet dispenser PCB. Drives an A4988 stepper (200 steps/rev, 16 microsteps) to feed one pellet per button press (FEED_BTN = pin 15).

**Flash target:** Raspberry Pi Pico on the dispenser PCB

### `tests/component_unit_tests/mice_door/mice_door.ino`

Controls the linear actuator for the mice door.

**Flash target:** Door actuator controller board

---

## Utility Test Scripts (run on Pi or laptop)

| Script | Where to run | What it does |
|---|---|---|
| `tests/linear_sensor/csv_log_only.py` | Pi | GPIO-synced per-sample CSV logger, uncapped rate |
| `tests/linear_sensor/LXK_monitoring.py` | Pi or laptop | Continuous terminal readout with light smoothing |
| `tests/linear_sensor/LXK_live_vals.py` | Pi or laptop | Raw high-speed sampling rate benchmark (reports Hz every 5 s) |
| `tests/linear_sensor/mice_step_fn_mimic/mice_step_fn_mimic_csv_log.py` | Pi or laptop | GPIO-free cycle logger using software threshold detection |

---

## Installation

```bash
# On the Pi (or development machine):
pip install pyserial matplotlib flask RPi.GPIO
```

> `RPi.GPIO` is only required on the Pi for scripts that use GPIO sync. Laptop-only scripts (`live_graph_pos.py`, `LXK_*.py`) do not need it.

---

## Notes

- The calibration table in `components/LinearSensor/serial_reader.py` was last updated 2026-06-04. Re-run `tests/linear_sensor/calibration/` scripts and update the table after sensor replacement or repositioning.
- `run_core/main.py` requires `pigpio` (Pi 4 only). Do not run on Pi 5.
- All scripts resolve the project root via `Path(__file__).resolve().parents[N]` — always run scripts from their own directory or with a full path, not from an arbitrary working directory.
