import serial
import time
from datetime import datetime

class LinearSensorReader:
    def __init__(self, port='COM3', baudrate=19200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

        self.calibration_table = [
        (0.000, 10385),
        (0.635, 10296),
        (1.270, 10219),
        (1.905, 10137),
        (2.540, 10047),
        (3.175, 9959),
        (3.810, 9868),
        (4.445, 9768),
        (5.080, 9666),
        (5.715, 9562),
        (6.350, 9484),
        (6.985, 9421),
        (7.620, 9374),
        (8.255, 9318),
        (8.890, 9187),
        (9.525, 8980),
        (10.160, 8831),
        (10.795, 8694),
        (11.430, 8533),
        (12.065, 8408),
        (12.700, 8263),
        (13.335, 8162),
        (13.970, 8068),
        (14.605, 7988),
        (15.240, 7876),
        (15.875, 7797),
        (16.510, 7716),
        (17.145, 7613),
        (17.780, 7522),
        (18.415, 7389),
        (19.050, 7250),
        (19.685, 7136),
        (20.320, 7041),
        (20.955, 6903),
        (21.590, 6802),
        (22.225, 6699),
    ]

    def connect(self):
        """Connect to the sensor"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from sensor"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Disconnected")

    def send_command(self, command):
        """Send a single character command"""
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
        """Get position reading using 'F' command"""
        response = self.send_command('F')
        if response:
            try:
                hex_part = response.split()[0]  # Get "04A3" part
                decimal_value = int(hex_part, 16)
                return decimal_value, response
            except:
                return None, response
        return None, response

    def interpolate(self, raw_value):
        """Interpolate raw sensor value to mm using calibration table"""
        table = self.calibration_table

        if raw_value >= table[0][1]:
            return table[0][0]
        if raw_value <= table[-1][1]:
            return table[-1][0]

        for i in range(len(table)-1):
            mm1, r1 = table[i]
            mm2, r2 = table[i+1]
            if r2 <= raw_value <= r1:
                ratio = (raw_value - r1) / (r2 - r1)
                return mm1 + ratio * (mm2 - mm1)

        return None

    def get_status(self):
        """Get status using 'G' command"""
        return self.send_command('G')

    def get_device_info(self):
        """Get device info using 'A' command"""
        return self.send_command('A')

    def continuous_monitoring(self, interval=0.1):
        """Continuously monitor position with smoothing"""
        self.running = True
        print("Starting continuous monitoring (Press Ctrl+C to stop)")
        print("Timestamp\t\tRaw\t\tmm\t\tFull Response")
        print("-" * 100)

        smoothed_mm = None
        alpha = 0.05  # smoothing factor: smaller = smoother

        try:
            while self.running:
                raw_value, raw_response = self.get_position()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                if raw_value is not None:
                    mm_value = self.interpolate(raw_value)

                    # --- Low-pass filter ---
                    # if smoothed_mm is None:
                    #     smoothed_mm = mm_value
                    # else:
                    #     smoothed_mm = alpha * mm_value + (1 - alpha) * smoothed_mm

                    print(f"{timestamp}\t{raw_value}\t\t{mm_value:.3f} mm\t{raw_response}")
                else:
                    print(f"{timestamp}\t{raw_response}\t\t(Parse Error)")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping monitoring...")
            self.running = False

if __name__ == "__main__":
    sensor = LinearSensorReader('COM3', 19200)

    if sensor.connect():
        print("\n=== Testing Commands ===")

        print("Position:", sensor.get_position())
        print("Status:", sensor.get_status())
        print("Device Info:", sensor.get_device_info())

        response = input("\nStart continuous monitoring? (y/n): ")
        if response.lower() == 'y':
            sensor.continuous_monitoring()

        sensor.disconnect()
    else:
        print("Failed to connect to sensor")