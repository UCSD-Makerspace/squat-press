# Pico SENT viewer (LX3302A lift-height + velocity dashboard)

Full-rate live viewer for the LX3302A inductive position sensor. A Raspberry Pi Pico
(RP2040, MicroPython) times the sensor's SENT output edge-to-edge with a PIO state
machine and forwards the raw gap counts over USB as framed binary; the host (a
Raspberry Pi 5, or any PC) decodes the whole stream in numpy and plots it. Doing the
decode on the host keeps the sensor at full rate and shows every frame.

The dashboard (Tesla-instrument style): **Lift Height (cm, green)** stacked over
**Velocity (cm/s, blue)** on a shared rolling time axis, plus a **Frequency**
speedometer (with a `--set-freq` setpoint marker) and **SENT / CRC / LOSS** tiles.
It uses manual blitting for a smooth ~30 fps on the Pi.

## Files
- `pico_pc.py`   — the viewer (decode + dashboard). Run this.
- `pico_live.py` — Pico bring-up helpers (`start_pico`, `pick_port`); imported by `pico_pc.py`.
- `calibration.json` — host calibration `{"table": [[mm, count], ...]}`, linear-interpolated.
  Current 2-point micrometer cal: `3488 -> 0 mm (0 in)`, `466 -> 22.86 mm (0.9 in)`.
- `deploy_view.sh` — launch helper for the Pi (frees the port, harvests the Wayland
  session env, detaches the viewer onto the Pi's display).

## Run locally (sensor's Pico plugged into this machine)
```
python3 pico_pc.py --window 15 --set-freq 500     # cm, 15 s window
python3 pico_pc.py --counts                        # raw 0-4095 SENT counts
python3 pico_pc.py --csv run.csv                   # also log device_t,pos,status (full rate)
```
Useful flags: `--port COM5|/dev/ttyACM0`, `--interval 33` (redraw ms, ~30 fps),
`--decimate 10` (plot every Nth frame; capture/CSV stay full rate), `--no-max`.

## Deploy to the Raspberry Pi 5 (over SSH)
The Pi must already have `pico_pc.py`, `pico_live.py`, `calibration.json`,
`deploy_view.sh` in `~/induction/` and the Pico connected by USB.

1. Push an updated file (from the PC; SFTP is unreliable on this link, so a `cat >`
   channel is used). Example with the repo's helper scripts:
   ```
   python pi_putfile.py pico_pc.py /home/pi/induction/pico_pc.py
   ```
2. Launch it on the Pi's own monitor:
   ```
   ssh pi@<pi-ip> 'sed -i "s/\r$//" ~/induction/deploy_view.sh; \
                    bash ~/induction/deploy_view.sh pico_pc.py --window 15 --set-freq 500'
   ```
   `deploy_view.sh` kills any running viewer, finds the `/dev/ttyACM*` port, harvests the
   desktop session env (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, `XAUTHORITY`,
   `XDG_RUNTIME_DIR`) from a GUI process, and `setsid`-detaches the viewer.

Notes:
- Strip CRLF after copying `deploy_view.sh` to the Pi (`sed -i "s/\r$//" deploy_view.sh`)
  or bash fails with exit 127.
- The sensor's LX3302A calibration must be **programmed to EEPROM** (live cal does not
  persist); otherwise the Pico reads garbage after a power-cycle.
- Write Python files as real UTF-8 — Windows PowerShell 5.1 `Get/Set-Content` corrupts
  the `●` / `•` glyphs used in the dashboard.
