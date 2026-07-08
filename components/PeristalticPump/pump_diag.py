#!/usr/bin/env python3
"""READ-ONLY diagnostic: dump every relevant Kamoer driver register. Sends NO motor commands.
Usage: python pump_diag.py [port]   (default COM8 on Windows, /dev/ttyUSB0 elsewhere)"""
import sys, time
from pymodbus.client import ModbusSerialClient
PORT = sys.argv[1] if len(sys.argv) > 1 else ("COM8" if sys.platform.startswith("win") else "/dev/ttyUSB0")
c = ModbusSerialClient(port=PORT, baudrate=9600, parity="N", stopbits=1, bytesize=8, timeout=0.4, retries=1)
if not c.connect():
    print("cannot open COM8 (is the GUI still open? close it first)"); raise SystemExit(1)

def rd(reg, n=1):
    try:
        r = c.read_holding_registers(reg, count=n, device_id=1)
        v = list(r.registers) if (r is not None and hasattr(r, "registers")) else None
    except Exception as e:
        v = f"ERR {e}"
    time.sleep(0.07); return v

def u32(reg):  # 32-bit, low word first
    v = rd(reg, 2)
    if isinstance(v, list) and len(v) == 2:
        return v[0] | (v[1] << 16)
    return v

print("step_angle 0x0000 :", rd(0x0000))
print("subdivision0x0001 :", rd(0x0001))
print("start_freq 0x0002 :", rd(0x0002))
print("accel_freq 0x0003 :", rd(0x0003))
print("PITCH 0x0004-5    :", u32(0x0004), " (raw", rd(0x0004,2), ")")
print("stop_mode 0x0007  :", rd(0x0007))
print("speed 0x0008      :", rd(0x0008))
print("CIRCLES 0x0009-A  :", u32(0x0009), " (raw", rd(0x0009,2), ")")
print("direction 0x000B  :", rd(0x000B))
print("dev_id 0x0010     :", rd(0x0010))
print("STATUS 0x0030     :", rd(0x0030), " (1=running 0=stopped)")
print("enable 0x004F     :", rd(0x004F), " (0=enabled 1=disabled)")
pitch = u32(0x0004); circ = u32(0x0009)
try:
    print(f"\n--> single-step should run circles/pitch = {circ}/{pitch} = {circ/pitch:.3f} revolutions")
except Exception:
    pass
c.close()
