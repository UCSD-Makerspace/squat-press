import serial
import time
import threading
from datetime import datetime
from pathlib import Path
import importlib.util


def get_serial_port(default="ACM1"):
    s = input(f"Serial port (e.g. ACM1 or /dev/ttyACM1) [{default}]: ").strip()
    if not s:
        s = default
    if s.startswith("/dev/") or s.startswith("COM"):
        return s
    s_low = s.lower()
    if s_low.startswith("acm"):
        return f"/dev/tty{s_low}"
    if s_low.isdigit():
        return f"/dev/ttyACM{s_low}"
    return s


class LinearSensorReader:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        self._stop_event = threading.Event()
        self._reader_thread = None

        # Stats
        self._stats_start_time = None
        self._stats_end_time = None
        self._total_samples = 0
        self._total_errors = 0

        # Load calibration table
        cal_path = Path(__file__).resolve().parents[1] / "calibration" / "calibration_table.py"
        spec = importlib.util.spec_from_file_location("calibration_table", cal_path)
        cal_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cal_mod)
        self.calibration_table = cal_mod.calibration_table

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.02)
            print(f"Connected to {self.port} at {self.baudrate} baud")

            # Warmup
            for _ in range(10):
                self.ser.write(b'F')
                self.ser.readline()
                time.sleep(0.005)

            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        self._stop_event.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Disconnected")

    def interpolate(self, raw_value):
        table = self.calibration_table

        if raw_value >= table[0][1]:
            return table[0][0]
        if raw_value <= table[-1][1]:
            return table[-1][0]

        for i in range(len(table) - 1):
            mm1, r1 = table[i]
            mm2, r2 = table[i + 1]

            if r2 <= raw_value <= r1:
                ratio = (raw_value - r1) / (r2 - r1)
                return mm1 + ratio * (mm2 - mm1)

        return None

    # ── High-speed reader ─────────────────────────────────────────────

    def _reader_loop(self):
        count = 0
        t_report = time.time()

        while not self._stop_event.is_set():
            try:
                self.ser.write(b'F')
                resp = self.ser.readline().decode('ascii', errors='replace').strip()

                if resp:
                    raw = int(resp.split()[0], 16)
                    mm = self.interpolate(raw)

                    if mm is not None:
                        self._total_samples += 1
                        count += 1
                    else:
                        self._total_errors += 1
                else:
                    self._total_errors += 1

            except Exception:
                self._total_errors += 1

            now = time.time()

            # Print instantaneous rate every 5 seconds
            if now - t_report >= 5.0:
                rate = count / (now - t_report)
                print(f"[reader] {rate:.0f} Hz")
                count = 0
                t_report = now

    def start(self):
        self._stop_event.clear()

        self._stats_start_time = time.time()
        self._total_samples = 0
        self._total_errors = 0

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True
        )
        self._reader_thread.start()

        print("Running raw sampling test...")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")

        self._stop_event.set()
        self._stats_end_time = time.time()

        self._print_summary()

    def _print_summary(self):
        duration = self._stats_end_time - self._stats_start_time

        avg_hz = self._total_samples / duration if duration > 0 else 0

        print("\n=== Sampling Summary ===")
        print(f"Duration:        {duration:.2f} s")
        print(f"Total samples:   {self._total_samples}")
        print(f"Total errors:    {self._total_errors}")
        print(f"Average rate:    {avg_hz:.2f} Hz")


if __name__ == "__main__":
    port = get_serial_port()
    sensor = LinearSensorReader(port, 921600)

    if sensor.connect():
        sensor.start()
        sensor.disconnect()
    else:
        print("Failed to connect to sensor")