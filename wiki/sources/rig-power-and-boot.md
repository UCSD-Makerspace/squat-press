# Source: rig power & boot behavior

Immutable ground-truth notes on how the rig powers up and boots. Append-only.

## Power-on → auto-boot (confirmed 2026-09-24)
- **One switched supply powers the rig. Turning it on powers the Raspberry Pi 5, which auto-boots
  straight to its desktop** — no key press needed. (User: *"powering on the devices auto turns on the
  pi + desktop."*)
- Verified remotely right after switch-on: `hostname` = `raspberrypi`, `uptime` ≈ **2 min** (fresh boot),
  and all three USB serial devices already enumerated: `/dev/ttyACM0`, `/dev/ttyACM1`, `/dev/ttyUSB0`.
- **Why it auto-boots:** a Raspberry Pi has **no power button** — it boots whenever 5 V is applied. After
  `sudo shutdown -h now` it *halts and stays off* until power is **cut and re-applied**; re-applying power
  boots it again. There is no "wake" command — you power-cycle.

## What comes up on power (USB serial map)
- Two RP2040 Picos → `/dev/ttyACM*`: one is the **sensor** node (LX3302A via SENT), one is the **pump**
  (TMC2209). The rail (Oriental Motor AZD-KD) via a **CP210x / SH-U10** adapter → `/dev/ttyUSB0`.
- **Enumeration order is NOT fixed** — which Pico is `ttyACM0` vs `ttyACM1` can swap between boots. The
  app therefore resolves roles **by content, never by port**: pump = the ACM whose flash carries `pump.py`,
  sensor = the other bare ACM, rail = the ttyUSB.

## After boot
- The desktop is up, but the **dosing app does NOT auto-start** (no `@reboot`/systemd unit as of
  2026-09-24). It's launched after boot — via the **Start Rig** desktop icon (`rig_start.sh` →
  `run_pump_app.sh`) or a terminal.
- The compare/dashboard tool (`pico_pc` / `rail_vs_sensor`) is a *separate* app with its own
  `stop_app.sh`; it is not the dosing app.

## Power sequencing rule (24 V)
- The 24 V motor supply comes up on the same switch as the Pi's 5 V. Because the desktop takes ~20–30 s to
  come up before the app is launched, **24 V is already stable by the time the app starts** — which is the
  correct order (24 V up *before* the app).
- **Never toggle 24 V while the app is running** — the transient knocks the pump/rail off the USB bus and
  freezes the app. Sequence: power on (Pi + 24 V) → wait for desktop → Start Rig; to stop: Stop Rig (app
  down) → then 24 V off.

## Network
- Pi = **192.168.137.50** (static), reached from the PC over a Windows **ICS** Ethernet share (PC =
  192.168.137.1). SSH user `pi`.
