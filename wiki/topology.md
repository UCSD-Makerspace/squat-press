# System topology — power, boot, and device map

*Compiled from: [rig-power-and-boot](sources/rig-power-and-boot.md). Related: [peristaltic-pump](peristaltic-pump.md).*

How the squat-press rig is wired for power and control, and what happens from flipping the switch to a
running app.

## Power domains

```
   wall / switched supply
        │
        ├── 5 V ──► Raspberry Pi 5  ──(USB)──► the two Picos + the rail adapter
        │                                        (Picos are powered from the Pi's USB, NOT from 24 V)
        └── 24 V ─► rail motor (AZD-KD)  +  pump motor (TMC2209 VMOT)
```

- **One switch turns the whole rig on.** It powers the Pi's 5 V *and* the 24 V motor rail together.
- **The Picos run on USB 5 V from the Pi**, so switching the 24 V off does not disturb the sensor/pump
  logic — 24 V is *motor power only*.

## Boot sequence (hands-off)

1. **Flip the supply on.** The Pi has no power button, so applying 5 V **auto-boots it to the desktop**
   (~20–30 s). 24 V is up the whole time.
2. **USB devices enumerate:** the sensor Pico and pump Pico appear as `/dev/ttyACM*`, the rail as
   `/dev/ttyUSB0`. Their order can shuffle between boots — that's expected.
3. **Desktop is up, but the dosing app is not running yet.** Start it (see below).
4. **Start Rig** → the app auto-detects the three devices by content, injects the SENT decoder into the
   (blank) sensor Pico and verifies the stream, starts its threads, and opens the GUI on the Pi's screen.

To fully power down: **Stop Rig** (app down) → switch **24 V/​supply off**. `sudo shutdown -h now` halts the
Pi; it stays off until power is cut and re-applied (which re-boots it).

## Device / port map

| Role | Device | Identified by |
|---|---|---|
| **Sensor** (LX3302A → SENT) | `/dev/ttyACM*` (bare Pico) | the ACM that is *not* the pump |
| **Pump** (TMC2209) | `/dev/ttyACM*` (Pico with `pump.py`) | flash carries `pump.py` |
| **Rail** (AZD-KD, Modbus/RS-485) | `/dev/ttyUSB0` (CP210x/SH-U10) | VID 0x10C4 / ttyUSB |

Ports are resolved **by content, never hard-coded** — see [peristaltic-pump](peristaltic-pump.md) and the
app's device-detection, because enumeration order isn't stable across reboots.

## Start / stop (on the Pi, no SSH)

- **Start Rig** desktop icon → `~/induction/rig_start.sh` → `run_pump_app.sh` (auto-detect + arm + GUI).
- **Stop Rig** desktop icon → `~/induction/rig_stop.sh` (stops the app, frees the ports; then switch 24 V off).
- Closing the app's GUI window is also a clean stop (it de-energizes the pump on exit).

## The one hard rule

**Never toggle 24 V while the app is running.** Bring 24 V up before launching (the boot order does this for
you) and switch it off only after the app is stopped. Toggling it live crashes the pump/rail off the USB bus.

## Network

Pi at **192.168.137.50** (static) via the PC's Windows **ICS** Ethernet share (PC = 192.168.137.1); SSH user `pi`.
