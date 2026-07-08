# SOURCE — Kamoer MODBUS-RTU Stepper Pump Driver

> Immutable extract. Primary: *MODBUS-RTU Stepper Peristaltic Pump Driver
> Instructions*, A3 (2021-12-11), Kamoer Fluid Tech; order no. **10.10.0013**
> ("MODBUS-RTU Standard Edition Driver"). PDF held locally in the lab Downloads.

## Device
- 2-phase stepper driver for Kamoer peristaltic pumps. DC 9–42 V, max 150 W.
- Max **32** microsteps. Drive current DIP-selectable: 0.7 / 1.2 / 1.7 / 2.2 / 2.7 / 2.9 / 3.2 / 4.0 A.
- Four control modes: built-in pot, external pot, 0–10 V, **MODBUS-RTU (RS-485)**.
- Two start/stop modes: **trigger** (momentary/self-resetting) and **jog** (level/self-locking).

## Comms
- `9600` baud, `8` data, `1` stop, **no parity**. Default device address `1`.
- Big-endian data; CRC low byte first. 32-bit value = 2 registers, **low word first**.
- Response time per frame ≥ **35 ms**.
- Modbus decimal → protocol hex: `40001` → `0x0000`, `40010` → `0x0009`, etc.

## Holding registers (fn 03 read / 06,10 write)
| Modbus | Protocol | Meaning |
|---|---|---|
| 40001 | 0x0000 | Step angle ×100 (1.8° → 180) |
| 40002 | 0x0001 | Subdivision (1/2/4/8/16/32) — must equal DIP SW7-9 |
| 40003 | 0x0002 | Start frequency (Hz) |
| 40004 | 0x0003 | Accel/decel frequency (Hz) |
| 40005-06 | 0x0004-05 | Pitch = circle-units per revolution (default 100) |
| 40007 | 0x0006 | Fixed value 0 (unused) |
| 40008 | 0x0007 | Stop mode (0 slow / 1 immediate) |
| 40009 | 0x0008 | Speed (RPM) |
| 40010-11 | 0x0009-0A | Single-step circles, 32-bit low-first |
| 40012 | 0x000B | Direction (0 fwd / 1 rev) |
| 40017 | 0x0010 | Device ID (485 address) |
| 40049 | 0x0030 | Running status (1 run / 0 stop) |
| 40074-75 | 0x0049-4A | Baud rate, 32-bit low-first |
| 40080 | 0x004F | Motor enable (0 en / 1 dis) |

## Coils (fn 01 read / 05 write; `0xFF00` = ON, `0x0000` = OFF)
| Coil | Meaning |
|---|---|
| 0x0000 | Save all parameters to flash |
| 0x0004 | Forward — ON runs continuously, OFF stops (level) |
| 0x0005 | Reverse |
| 0x0007 | Single-step — runs the set circles **once** (momentary trigger) |

## DIP switches
- RS-485 mode: SW1–SW5 **OFF**, SW6 **ON**.
- Subdivision SW7/8/9: `ON ON OFF`=1, `ON OFF ON`=2, `ON OFF OFF`=4, `OFF ON OFF`=8, `OFF OFF ON`=16, `OFF OFF OFF`=32.
- Current SW10/11/12: `ON ON ON`=0.5A, `ON OFF ON`=1A, `ON ON OFF`=1.5A, `ON OFF OFF`=2A, …
- Board latches DIPs at power-up only → power-cycle after changes.

## Single-step / fixed dose (manual §2.4.4.8–9)
- **Revolutions per single-step = circles ÷ pitch.** With pitch=100, circles=75 → 0.75 rev; circles=200 → 2 rev.
- Sequence: write circles (0x0009-0A), write speed (0x0008, non-zero), then **pulse** coil 0x0007 ON→OFF.
- The move is a fixed pulse count and self-stops; subdivision does not change the revolution count *provided register = DIP*.

## Observed behaviour / gotchas (lab, 2026-07)
- **Subdivision register must equal the DIP** or single-step scales by `reg÷dip` (e.g. reg 32 vs DIP 8 → 4× over-rotation).
- Holding coil 0x0007 HIGH re-triggers → continuous run; must pulse.
- Comms is flaky *while the motor spins* — pace frames ≥ 70 ms and use per-op retry loops; "Cleanup recv buffer" lines are stale-frame noise.
- Confirmed stop = coils 0x0004/0x0005/0x0007 OFF + speed 0, then read 0x0030 until 0.
