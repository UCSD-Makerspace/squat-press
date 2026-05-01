"""
Microchip IPCE Continuous Data Capture via TCP/IP
==================================================
  Host IP : 172.27.112.1
  Port    : 26490

USAGE:
    python ipce_capture.py --sniff
    python ipce_capture.py
    python ipce_capture.py --interval 0.05 --output my_run.csv
"""

import socket
import time
import csv
import argparse
import sys
from datetime import datetime

DEFAULT_HOST     = "172.27.112.1"
DEFAULT_PORT     = 26490
DEFAULT_INTERVAL = 1.0
DEFAULT_OUTPUT   = "sensor_log.csv"
CMD_READ         = "F\r\n"   # Update this after --sniff tells you what works


def connect(host, port, timeout=5.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        print(f"[OK] Connected to IPCE at {host}:{port}")
        return sock
    except ConnectionRefusedError:
        print(f"\n[ERROR] Connection refused at {host}:{port}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


def send_command(sock, command, read_timeout=0.1):
    """Send command, return response string (empty string if no response)."""
    try:
        sock.sendall(command.encode("ascii"))
    except Exception as e:
        print(f"[ERROR] Send failed: {e}")
        sys.exit(1)
    sock.settimeout(read_timeout)
    chunks = []
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk.decode("ascii", errors="replace"))
            if chunks[-1].endswith("\n"):
                break
    except socket.timeout:
        pass
    return "".join(chunks).strip()


def sniff_protocol(sock):
    print("\n[SNIFF] Testing commands — watch 'network traffic log' in IPCE too\n")

    # Only the most likely candidates, 100ms timeout each = completes in ~10s total
    candidates = []
    for char in "FGABCDEfgabcde":
        for ending in ["\r\n", "\r", "\n", ""]:
            candidates.append(char + ending)
    for cmd in ["STATUS\r\n", "READ\r\n", "GETDATA\r\n", "CAPTURE\r\n", "GET\r\n", "PING\r\n"]:
        candidates.append(cmd)

    found_any = False
    for payload in candidates:
        resp = send_command(sock, payload, read_timeout=0.1)
        if resp:
            print(f"  {repr(payload):20s} -> '{resp}'")
            found_any = True

    if not found_any:
        print("  No commands got a response.")
        print()
        print("  Next steps:")
        print("  1. Check IPCE 'network traffic log' — did bytes appear while sniff ran?")
        print("     YES -> bytes arrive but IPCE doesn't respond. May need Advanced Mode login first.")
        print("     NO  -> bytes aren't reaching IPCE. Firewall or wrong IP.")
        print("  2. Try logging into Advanced Mode in IPCE (the login dialog you saw),")
        print("     then re-run --sniff.")

    print("\n[SNIFF DONE]\n")


def parse_response(response):
    data = {"raw": response}
    if not response:
        return data
    if "=" in response:
        for pair in response.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                data[k.strip().upper()] = v.strip()
    else:
        cols = ["IO1", "IO2", "IO3", "VIN", "RAW_COS", "RAW_SIN", "OSC", "OUTPUT", "RADIUS"]
        for i, val in enumerate(response.split(",")):
            data[cols[i] if i < len(cols) else f"FIELD_{i}"] = val.strip()
    return data


def capture_loop(host, port, interval, output_file, max_samples):
    sock = connect(host, port)
    csv_file = open(output_file, "w", newline="", encoding="utf-8")
    writer = None

    print(f"\n[CAPTURE] {1/interval:.1f}Hz -> {output_file}  (Ctrl+C to stop)\n")

    sample_count = 0
    try:
        while True:
            if max_samples and sample_count >= max_samples:
                print(f"\n[DONE] {max_samples} samples captured.")
                break

            response = send_command(sock, CMD_READ, read_timeout=1.0)
            timestamp = datetime.now().isoformat(timespec="milliseconds")
            parsed = parse_response(response)
            parsed["timestamp"] = timestamp
            parsed["sample"] = sample_count + 1

            if writer is None:
                priority = ["sample", "timestamp"]
                rest = [k for k in parsed if k not in priority]
                writer = csv.DictWriter(csv_file, fieldnames=priority + rest, extrasaction="ignore")
                writer.writeheader()

            writer.writerow(parsed)
            csv_file.flush()
            sample_count += 1

            display = parsed.get("OUTPUT", parsed.get("IO1", response[:50] if response else "(empty)"))
            print(f"  [{sample_count:>5}] {timestamp}  {display}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[STOPPED] {sample_count} samples -> {output_file}")
    finally:
        csv_file.close()
        sock.close()


def main():
    p = argparse.ArgumentParser(description="Microchip IPCE continuous capture via TCP/IP")
    p.add_argument("--host",     default=DEFAULT_HOST)
    p.add_argument("--port",     default=DEFAULT_PORT, type=int)
    p.add_argument("--interval", default=DEFAULT_INTERVAL, type=float)
    p.add_argument("--output",   default=DEFAULT_OUTPUT)
    p.add_argument("--samples",  default=0, type=int)
    p.add_argument("--sniff",    action="store_true", help="Probe IPCE for working commands then exit")
    args = p.parse_args()

    sock = connect(args.host, args.port)
    if args.sniff:
        sniff_protocol(sock)
        sock.close()
        return
    sock.close()
    capture_loop(args.host, args.port, args.interval, args.output, args.samples)


if __name__ == "__main__":
    main()