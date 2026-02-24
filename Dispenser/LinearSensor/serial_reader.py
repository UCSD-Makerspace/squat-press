import serial
import time
from datetime import datetime

class LinearSensorReader:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

        self.calibration_table = [
            (0.000, 10646),
            (1.000, 10488),
            (2.000, 10361),
            (3.000, 10207),
            (4.000, 10068),
            (5.000, 9900),
            (6.000, 9689),
            (7.000, 9600),
            (8.000, 9508),
            (9.000, 9392),
            (10.000, 9189),
            (11.000, 8922),
            (12.000, 8682),
            (13.000, 8447),
            (14.000, 8273),
            (15.000, 8097),
            (16.000, 7922),
            (17.000, 7773),
            (18.000, 7626),
            (19.000, 7425),
            (20.000, 7253),
            (21.000, 7017),
            (22.000, 6794),
            (23.000, 6578),
            (24.000, 6418),
            (25.000, 6193),
        ]

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
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
        response = self.send_command('F')

        if response:
            try:
                hex_part = response.split()[0]
                decimal_value = int(hex_part, 16)
                return self.interpolate(decimal_value)
            except Exception as e:
                print(f"Parse error in serial_reader get_position: {e}, raw response = {response}")
                return None
        return None

    def interpolate(self, raw_value) -> float:
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

        return -1.0

    def get_status(self):
        return self.send_command('G')

    def get_device_info(self):
        return self.send_command('A')