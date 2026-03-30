import serial
import time
from datetime import datetime

class LinearSensorReader:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

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
                hex_part = response.split()[0]
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

    def continuous_monitoring(self, interval=0.025, filter_window = 5, noise_threshold = 0.06):
        """Continuously monitor position with smoothing"""
        self.running = True
        print("Starting continuous monitoring (Press Ctrl+C to stop)")
        print("Timestamp\t\tRaw\t\tmm\t\tFull Response")
        print("-" * 100)

        recent_pos = []

        try:
            while self.running:
                raw_value, raw_response = self.get_position()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                if raw_value is not None:
                    mm_value = self.interpolate(raw_value)
                    if mm_value is None:
                        continue
                    recent_pos.append(mm_value)
                    if len(recent_pos) > filter_window:
                        recent_pos.pop(0)

                    filtered_value = sum(recent_pos) / len(recent_pos)
                    if abs(mm_value - filtered_value) > noise_threshold:
                        display_value = filtered_value  
                    else:
                        display_value = mm_value

                    print(f"{timestamp}\t{raw_value}\t\t{display_value:.3f} mm\t{raw_response}")
                else:
                    print(f"{timestamp}\t{raw_response}\t\t(Parse Error)")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping monitoring...")
            self.running = False

if __name__ == "__main__":
    sensor = LinearSensorReader("/dev/ttyACM1", 115200)

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