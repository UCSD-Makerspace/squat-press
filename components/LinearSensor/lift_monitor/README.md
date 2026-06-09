# continuous_lift_monitor

Always-on lift tracking for the linear position sensor. No start/stop recording -- it runs continuously, detects valid lifts automatically, and saves each one to a timestamped CSV.

---

## Usage

Run from the repo root:

```bash
# headless (no graph)
python -m components.LinearSensor.lift_monitor.main

# with live graph
python -m components.LinearSensor.lift_monitor.main --gui

# specify port explicitly
python -m components.LinearSensor.lift_monitor.main COM3 --gui

# specify sensor number (used in output filenames)
python -m components.LinearSensor.lift_monitor.main --gui --sensor 2
```

### Flags

| Flag | Default | Description |
|---|---|---|
| `<port>` | auto-detect | Serial port hint, e.g. `COM3` or `/dev/ttyACM0`. Overrides `port` in config. |
| `--gui` | off | Launch live scrolling graph window |
| `--sensor N` | 1 | Sensor number embedded in all output filenames |

---

## Startup calibration

On launch the script polls 15 live readings so you can verify the zero offset before monitoring begins.

```
Polling 15 live values for offset calibration...
  Current zero_offset_calibration = 0.0000 mm
  +0.0412 mm  (offset applied: 0.0000)
  +0.0398 mm  (offset applied: 0.0000)
  ...

  Y -- continue to monitoring
  R -- restart (reload config.cfg first, then re-poll)
  S -- stop / exit
```

If the sensor is reading a constant offset at rest (e.g. +0.04 mm), edit `lift_monitor.cfg`, set `zero_offset_calibration = 0.04`, then press **R** to reload and re-poll.

---

## Mid-session terminal controls

While the monitor is running, press **Enter** at any time to get the command menu:

| Key | Action |
|---|---|
| `R` | Reload `lift_monitor.cfg` from disk. Changes to thresholds, offsets, and cooldown take effect immediately on the next sample. |
| `S` | Print how many lifts have been confirmed this session. |
| `Q` | Gracefully stop the monitor (and close the GUI if open). |

`Ctrl+C` also works to stop.

### What hot-reloads immediately vs. on reconnect

| Setting | When it takes effect |
|---|---|
| `lift_threshold`, `min_lift_duration`, `drop_threshold`, `pellet_cooldown`, `zero_offset_calibration`, `window_size` | Immediately after `R` |
| `gui_window_size` | Immediately (read every animation frame) |
| `baud_rate`, `port` | Next sensor reconnect only |

---

## GUI controls (--gui only)

The graph window shows two subplots:

- **Top** -- live position (mm) with a scrolling window
- **Bottom** -- live sampling frequency (Hz)

### Line colours

| Colour | Meaning |
|---|---|
| Blue | Below lift threshold, or above threshold but not yet confirmed (duration not met) |
| Green | Confirmed valid lift |

### Reference lines

| Line | Meaning |
|---|---|
| Red dashed | `lift_threshold` -- must exceed to start a potential lift |
| Orange dotted | `drop_threshold` -- must fall below this after a lift before the next one arms |

### Cooldown shading

After each confirmed lift, an orange shaded band is drawn over the next `pellet_cooldown` seconds. Any lift event that fires within that window is flagged `within_cooldown = True` in its config snapshot (the pellet dispenser won't have cycled yet).

### State indicator (top-left of graph)

| State | Colour | Meaning |
|---|---|---|
| ARMED | Grey | Waiting for threshold crossing |
| PRE_LIFT | Amber | Above threshold, timing duration |
| CONFIRMED | Green | Valid lift in progress |
| COOLDOWN | Orange | Lift ended, waiting for drop + cooldown |

Closing the graph window stops the entire monitor.

---

## Output files

Saved to `data/csv/YYYY.MM.DD/` automatically.

Each confirmed lift produces two files:

```
sensor1_lift3_143022.csv
sensor1_lift3_143022_config.txt
```

### CSV format

```
time_s, position_mm, raw_value
-3.2041, 1.2341, 9987
-3.1993, 1.2289, 9990
...
0.0000, 19.2100, 7281    <- threshold crossed here
...
```

`time_s` is relative to the moment the threshold was first crossed (so pre-lift samples have negative timestamps). Total rows = up to `window_size` pre-lift samples + all samples during the lift.

### Config snapshot format

```
# Config snapshot for sensor1_lift3_143022
# lift_number      : 3
# peak_mm          : 21.43
# within_cooldown  : False
# samples          : 743
#
lift_threshold = 19.0
min_lift_duration = 0.04
...
```

---

## Config reference (`lift_monitor.cfg`)

Located at `components/LinearSensor/lift_monitor.cfg`.

| Key | Section | Default | Description |
|---|---|---|---|
| `port` | `[sensor]` | *(blank)* | Serial port. Leave blank for auto-detect. |
| `baud_rate` | `[sensor]` | `115200` | Serial baud rate. |
| `lift_threshold` | `[detection]` | `19.0` | Position (mm) sensor must exceed to start a potential lift. |
| `min_lift_duration` | `[detection]` | `0.040` | Seconds above threshold required to confirm a valid lift. |
| `drop_threshold` | `[detection]` | `5.0` | Position (mm) sensor must fall below after a lift before the next one can arm. |
| `pellet_cooldown` | `[detection]` | `3.0` | Seconds between consecutive confirmed lifts. Visualised in GUI; flags within-cooldown lifts in CSV. |
| `window_size` | `[recording]` | `600` | Pre-lift ring buffer size (samples captured before threshold crossing). At ~200-250 Hz, 600 samples ~= 3 seconds. |
| `zero_offset_calibration` | `[calibration]` | `0.0` | Constant offset (mm) subtracted from every reading. Set after startup calibration poll. |
| `gui_window_size` | `[gui]` | `10.0` | Width of the scrolling position window in seconds. |

---

## File structure

```
components/LinearSensor/
    lift_monitor.cfg          -- editable config (edit this)
    lift_monitor/
        main.py               -- entry point, calibration loop, terminal controls
        config.py             -- config loader with thread-safe hot-reload
        sensor_io.py          -- background serial polling thread, auto-reconnect
        lift_detector.py      -- ARMED->PRE_LIFT->CONFIRMED->COOLDOWN state machine
        csv_writer.py         -- saves CSV + config snapshot per lift event
        gui.py                -- optional live graph (--gui only)
        README.md             -- this file
```
