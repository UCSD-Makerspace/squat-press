#!/usr/bin/env python3
"""
pico_live.py - Live console dashboard for the LX3302A via the Pico SENT bridge.

Self-contained: on connect it pushes a small PIO SENT decoder into the Pico over
the REPL (paste mode), which then streams "P <pos> <status> <fps>" lines at ~20 Hz.
The host parses those and renders a self-refreshing dashboard:
  - SENT position (counts 0-4095) + live bar + calibrated mm
  - status nibble
  - on-wire frame rate (Hz)

Same decoder logic as pico_sent.py (PIO times falling-to-falling gaps; Python
decodes: tick=sync/56, nibble=round(gap/tick)-12, CRC-4 poly 0xD seed 0x3,
position=d1d2d3==d4d5d6). Needs only pyserial on the host -> runs on laptop & Pi.

Usage:
    python pico_live.py                 # auto-pick port, live dashboard, Ctrl-C quit
    python pico_live.py --port COM5
    python pico_live.py --csv out.csv   # also log host_time,pos,status
    python pico_live.py --plain         # non-refreshing (for piping/logs)
    python pico_live.py --seconds 5     # auto-stop after N s (demo)
"""
import sys, time, argparse, csv
import serial
from serial.tools import list_ports

LCLMP, HCLMP, TRAVEL_MM = 409, 3686, 50.0

# --- program pushed into the Pico (MicroPython). Indentation matters (paste mode). ---
PICO_PROG = r'''
import rp2,array,time
from machine import Pin
@rp2.asm_pio()
def fg():
    wait(1,pin,0)
    wait(0,pin,0)
    wrap_target()
    mov(x,invert(null))
    label("lo")
    jmp(pin,"hi")
    jmp(x_dec,"lo")
    label("hi")
    jmp(x_dec,"ck")
    label("ck")
    jmp(pin,"hi")
    in_(x,32)
    push(noblock)
    wrap()
def crc4(ns):
    c=3
    for n in ns:
        c^=n
        for _ in range(4):
            c=((c<<1)^0xD)&0xF if c&8 else (c<<1)&0xF
    return c
sm=rp2.StateMachine(0,fg,freq=8000000,in_base=Pin(15),jmp_pin=Pin(15))
N=450
buf=array.array('I',bytearray(4*N))
sm.active(1)
lp=0
ls=0
while True:
    t0=time.ticks_us()
    for i in range(N):
        buf[i]=sm.get()
    t1=time.ticks_us()
    g=[(0xFFFFFFFF-buf[i])&0xFFFFFFFF for i in range(N)]
    sg=sorted(g)
    th=1.8*sg[N//2]
    syn=[i for i in range(N) if g[i]>th]
    nf=0
    for k in range(len(syn)-1):
        s=syn[k]
        e=syn[k+1]
        tk=g[s]/56.0
        nb=[round(g[i]/tk)-12 for i in range(s+1,e)]
        if len(nb)==8 and all(0<=x<=15 for x in nb) and crc4(nb[1:7])==nb[7]:
            lp=(nb[1]<<8)|(nb[2]<<4)|nb[3]
            ls=nb[0]
            nf+=1
    el=time.ticks_diff(t1,t0)/1e6
    print("P",lp,ls,int(nf/el) if el>0 else 0)
'''


def enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass


def pick_port():
    for p in list_ports.comports():
        # Pico / RP2040 USB CDC = VID 0x2E8A
        if (p.vid == 0x2E8A) or ("2E8A" in (p.hwid or "").upper()):
            return p.device
    ports = list(list_ports.comports())
    return ports[0].device if ports else None


def bar(frac, width=40):
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * width))
    return "#" * n + "-" * (width - n)


def to_mm(sent):
    return max(0.0, min(TRAVEL_MM, (sent - LCLMP) / (HCLMP - LCLMP) * TRAVEL_MM))


def start_pico(ser, prog=None):
    prog = PICO_PROG if prog is None else prog
    # 1) Interrupt anything running, then SOFT-REBOOT the Pico (Ctrl-D at the REPL).
    #    The reboot frees all PIO/StateMachine state -- otherwise each relaunch loads
    #    another copy of the PIO program into the 32-slot PIO memory until creating a
    #    StateMachine fails with OSError(ENOMEM). Reboot = guaranteed clean slate.
    for _ in range(3):
        ser.write(b"\x03")
        time.sleep(0.1)
    time.sleep(0.1)
    ser.write(b"\x04")          # Ctrl-D: soft reboot
    time.sleep(0.9)             # let it reboot to a bare REPL (no main.py on this Pico)
    ser.reset_input_buffer()
    ser.write(b"\x03")          # ensure clean prompt
    time.sleep(0.1)
    # 2) Paste the decoder program.
    ser.write(b"\x05")          # Ctrl-E: paste mode
    time.sleep(0.2)
    for line in prog.strip("\n").split("\n"):
        ser.write((line + "\r").encode())
        time.sleep(0.003)       # pace lines so the USB-CDC buffer doesn't drop any
    time.sleep(0.2)
    ser.write(b"\x04")          # Ctrl-D: execute pasted block
    time.sleep(0.4)
    ser.reset_input_buffer()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = until Ctrl-C")
    args = ap.parse_args()

    port = args.port or pick_port()
    if not port:
        print("No serial port found. Plug in the Pico (or pass --port).")
        sys.exit(1)

    enable_ansi()
    ser = serial.Serial(port, 115200, timeout=1)
    print(f"Connecting to Pico on {port} ...")
    start_pico(ser)

    writer = None
    if args.csv:
        fcsv = open(args.csv, "w", newline="")
        writer = csv.writer(fcsv)
        writer.writerow(["host_time", "pos", "status"])

    smin, smax = 10**9, -10**9
    n = 0
    t0 = time.perf_counter()
    if not args.plain:
        sys.stdout.write("\033[2J")
    try:
        while True:
            if args.seconds and (time.perf_counter() - t0) >= args.seconds:
                break
            raw = ser.readline().decode("utf-8", "replace").strip()
            if not raw.startswith("P "):
                continue
            f = raw.split()
            if len(f) < 4:
                continue
            try:
                pos, status, fps = int(f[1]), int(f[2]), int(f[3])
            except ValueError:
                continue
            n += 1
            smin, smax = min(smin, pos), max(smax, pos)
            mm = to_mm(pos)
            if writer:
                writer.writerow([f"{time.time():.3f}", pos, status])

            if args.plain:
                print(f"pos={pos:4d}  {mm:6.2f}mm  status={status}  {fps:5d}Hz")
            else:
                out = ["\033[H"]
                out.append("  LX3302A live  (via Pico SENT bridge)                 \n")
                out.append("  " + "=" * 54 + "\n")
                out.append(f"  port      : {port:<40}\n")
                out.append(f"  frame rate: {fps:6d} Hz   (on-wire SENT)              \n")
                out.append(f"  samples   : {n:<8d} elapsed {time.perf_counter()-t0:6.1f}s\n")
                out.append("  " + "-" * 54 + "\n")
                out.append(f"  position  : {pos:5d} / 4095   ({pos/4095*100:5.1f}% FS)        \n")
                out.append(f"  distance  : {mm:6.2f} mm  (of {TRAVEL_MM:.0f} mm)               \n")
                out.append(f"  [{bar(pos/4095)}]\n")
                out.append(f"  status    : {status}                                        \n")
                out.append(f"  range seen: {smin} .. {smax}  (span {smax-smin})        \n")
                out.append("  " + "-" * 54 + "\n")
                out.append("  Move the target to watch it track.  Ctrl-C to quit.   \n")
                sys.stdout.write("".join(out))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ser.write(b"\x03")      # stop the Pico loop
        except Exception:
            pass
        ser.close()
        if writer:
            fcsv.close()
            print(f"\nLogged {n} samples to {args.csv}")


if __name__ == "__main__":
    main()
