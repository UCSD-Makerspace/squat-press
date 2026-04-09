import serial
import time
import threading
from datetime import datetime
from collections import deque


class LinearSensorReader:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

        # Rolling average config
        self._raw_buffer  = deque()          # (timestamp, mm) from background thread
        self._buffer_lock = threading.Lock()
        self._stop_event  = threading.Event()
        self._reader_thread = None

        self.calibration_table = [
            (0.000, 10615),
            (1.000, 10444),
            (2.000, 10284),
            (3.000, 10136),
            (4.000, 9992),
            (5.000, 9826),
            (6.000, 9644),
            (7.000, 9556),
            (8.000, 9463),
            (9.000, 9184),
            (10.000, 8982),
            (11.000, 8732),
            (12.000, 8457),
            (13.000, 8289),
            (14.000, 8125),
            (15.000, 7959),
            (16.000, 7789),
            (17.000, 7637),
            (18.000, 7447),
            (19.000, 7267),
            (20.000, 7042),
            (21.000, 6865),
            (22.000, 6684),
            (23.000, 6471),
            (24.000, 6254),
            (25.000, 6114),
        ]

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.02)
            print(f"Connected to {self.port} at {self.baudrate} baud")
            # Warm up — first few reads are often slow
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

    def send_command(self, command):
        """Send a single character command and return raw response string."""
        if not self.ser or not self.ser.is_open:
            print("Not connected!")
            return None
        try:
            self.ser.write(command.encode('ascii'))
            response = self.ser.readline().decode('ascii').strip()
            return response
        except Exception as e:
            print(f"Command error: {e}")
            return None

    def get_position(self):
        """Get position reading using 'F' command. Returns (decimal_value, raw_response)."""
        response = self.send_command('F')
        if response:
            try:
                decimal_value = int(response.split()[0], 16)
                return decimal_value, response
            except:
                return None, response
        return None, response

    def interpolate(self, raw_value):
        table = self.calibration_table
        if raw_value >= table[0][1]:
            return table[0][0]
        if raw_value <= table[-1][1]:
            return table[-1][0]
        for i in range(len(table) - 1):
            mm1, r1 = table[i]
            mm2, r2 = table[i+1]
            if r2 <= raw_value <= r1:
                ratio = (raw_value - r1) / (r2 - r1)
                return mm1 + ratio * (mm2 - mm1)
        return None

    def get_status(self):
        return self.send_command('G')

    def get_device_info(self):
        return self.send_command('A')

    # ── Background high-rate reader ───────────────────────────────────────────

    def _reader_loop(self):
        """
        Reads sensor as fast as serial allows with no sleep.
        Pushes (timestamp, mm) tuples into _raw_buffer.
        Prints achieved read rate every 5 seconds.
        """
        count    = 0
        t_report = time.time()

        while not self._stop_event.is_set():
            t0 = time.time()
            try:
                self.ser.write(b'F')
                resp = self.ser.readline().decode('ascii', errors='replace').strip()
                if resp:
                    raw = int(resp.split()[0], 16)
                    mm  = self.interpolate(raw)
                    if mm is not None:
                        with self._buffer_lock:
                            self._raw_buffer.append((t0, mm))
                        count += 1
            except Exception:
                pass

            now = time.time()
            if now - t_report >= 5.0:
                rate = count / (now - t_report)
                print(f"[reader] {rate:.0f} Hz raw read rate")
                count    = 0
                t_report = now

    def start_background_reader(self):
        """Start the high-rate background serial reader thread."""
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

    def get_smoothed_position(self, window_size=5):
        """
        Drain the raw buffer and return the rolling average of the last
        window_size readings. Returns (smoothed_mm, read_count) or (None, 0).
        """
        with self._buffer_lock:
            if not self._raw_buffer:
                return None, 0
            # Take all buffered samples
            samples = [mm for _, mm in self._raw_buffer]
            count   = len(self._raw_buffer)
            self._raw_buffer.clear()

        # Rolling average over last window_size values
        window  = samples[-window_size:]
        smoothed = sum(window) / len(window)
        return smoothed, count

    # ── Monitoring modes ──────────────────────────────────────────────────────

    def continuous_monitoring(
        self,
        output_hz=100,
        window_size=5,
    ):
        """
        High-rate background reader + fixed-rate smoothed output.

        output_hz   : how often to print/log a value (default 100Hz)
        window_size : rolling average window over raw samples
        """
        self.running = True
        self._stop_event.clear()
        self.start_background_reader()

        output_interval = 1.0 / output_hz
        next_tick       = time.time()

        print(f"Monitoring at {output_hz}Hz output, window={window_size} samples")
        print("(Background reader running as fast as serial allows)")
        print("Timestamp            smoothed_mm   raw_count")
        print("-" * 55)

        try:
            while self.running:
                smoothed, count = self.get_smoothed_position(window_size)
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                if smoothed is not None:
                    print(f"{timestamp}    {smoothed:7.3f} mm    ({count} reads)")
                else:
                    print(f"{timestamp}    (no data)")

                # Fixed-rate sleep
                next_tick += output_interval
                sleep_for  = next_tick - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    next_tick = time.time()

        except KeyboardInterrupt:
            print("\nStopping...")
            self.running = False
        finally:
            self._stop_event.set()


if __name__ == "__main__":
    sensor = LinearSensorReader("/dev/ttyACM1", 115200)

    if sensor.connect():
        print("\n=== Testing Commands ===")
        print("Position:", sensor.get_position())
        print("Status:  ", sensor.get_status())
        print("Device:  ", sensor.get_device_info())

        response = input("\nStart continuous monitoring? (y/n): ")
        if response.lower() == 'y':
            sensor.continuous_monitoring(output_hz=100, window_size=5)

        sensor.disconnect()
    else:
        print("Failed to connect to sensor")