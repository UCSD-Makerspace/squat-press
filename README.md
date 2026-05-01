# Squat-Press

Repository for the mice squat press system.

```
.
├── components/   - Decoupled subsystem drivers (LinearSensor, PhotoInterruptor, StepperMotor, TMC2209)
├── data/         - CSV captures and validation/analysis scripts for the LXK3302A
├── run_core/     - Synchronized runtime that coordinates all hardware via the PCB
└── tests/        - Unit tests, calibration scripts, and flashed Arduino sketches
```

## Installation

Run `install.sh` to install all required dependencies. 

'''
./install.sh
'''

## Hardware Setup

This system requires the [LX3302AL012 50mm Linear Inductive Position Sensor](https://www.microchip.com/en-us/development-tool/lxk3302al012) and a Raspberry Pi 4. (Note: A Pi 5 will not work with pigpio)

### Wiring

Use female-to-female dupont jumper wires to connect:
| PI               | LX3302A     |
| ---------------- | ----------- |
| Ground           | Ground      |
| 5v Power         | +5v supply  |
| GPIO 18 (pin 12) | IO 2 (SENT) |

![LX3302A](https://github.com/user-attachments/assets/7223d5bf-0087-47ec-a62d-9505fc646243)

![LX3302A Pinout](https://github.com/user-attachments/assets/a61832e2-810b-4193-ae6a-5ce1c3c29b71)

![Labeled Pi Pinout](https://github.com/user-attachments/assets/ff602767-0d61-4f26-b470-7c4de1c079db)




## Usage 

Run `run.sh` to run the basic SENT reader.
```
./run.sh
```

## Data

`/data` contains CSV captures and validation scripts for the LXK3302A linear sensor.

```
data/
├── csv/                  - Date-stamped capture sessions (sensor CSVs + golden-truth CSVs)
├── validation_scripts/
│   ├── multi_cycle/      - Analysis scripts comparing multi-cycle captures against ground truth
│   └── single_cycle/     - Single-cycle validation scripts
└── ipce_capture.py       - IPCE data capture utility
```

### Linear sensor validation scripts

**`multi_cycle/`**

- `all_cycles.py` — Plots all cycles from a capture session.
- `all_cycles_vs_gt.py` — Overlays all cycles against the ground-truth curve.

**`single_cycle/`**

- `auc_graph.py` — Computes and plots the area-under-curve (AUC) for the lift peak, comparing ground truth and sensor output.
- `single_cycle_rolling_avg.py` — Plots a single cycle using a rolling (bucket) average and searches for the best vertical offset that minimizes the error-under-curve vs ground truth.
- `single_cycle_vs_truth.py` — Same comparison without smoothing.
- `single_histogram.py` — Histograms of average timing error across the lift (lower-confidence metric).
- `tut_accuracy.py` — Computes time-under-tension accuracy for the peak eccentric phase vs ground truth.
- `velocity_graph.py` — Compares point-wise velocities between the sensor output and ground truth.
- `master_script.py` — Runs all single-cycle analyses in sequence.

#### Ground truth data

Ground-truth positions are extracted from 240 FPS slow-motion video recorded while running the ESP32 test routine in `tests/linear_sensor/accuator_unit_test_stepper/accuator_unit_test_stepper.ino`. That firmware reproduces a representative mice squat motion using velocity mappings on the linear actuator.

## Project layout

- `run_core/` — Synchronized runtime that coordinates all components; expects hardware wired via the PCB.
- `components/` — Decoupled subsystem drivers used by `run_core`: `LinearSensor`, `PhotoInterruptor`, `StepperMotor`, `TMC2209`.
- `tests/`
  - `linear_sensor/` — Live monitoring scripts, calibration utilities, rolling-average samplers, and the `accuator_unit_test_stepper` Arduino sketch used to generate ground-truth data.
  - `component_unit_tests/` — PCB-level unit tests for the dispenser motor (`dispenser_motor_pcb_test`) and mice door actuator.
  - `pellet_dispenser_a4988/` — Standalone Arduino sketch for the A4988-driven pellet dispenser.

