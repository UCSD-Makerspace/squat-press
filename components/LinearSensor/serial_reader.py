import serial
import time
from datetime import datetime

class   LinearSensorReader:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

        # Auto-generated calibration table
        # Generated on: 2026-04-09 13:21:28
        # Samples per point: 50

        self.calibration_table = [
            (0.000, 10664),
            (1.000, 10495),
            (2.000, 10377),
            (3.000, 10214),
            (4.000, 10050),
            (5.000, 9903),
            (6.000, 9718),
            (7.000, 9602),
            (8.000, 9511),
            (9.000, 9331),
            (10.000, 9065),
            (11.000, 8813),
            (12.000, 8524),
            (13.000, 8329),
            (14.000, 8216),
            (15.000, 8030),
            (16.000, 7840),
            (17.000, 7734),
            (18.000, 7524),
            (19.000, 7332),
            (20.000, 7155),
            (21.000, 6959),
            (22.000, 6760),
            (23.000, 6498),
            (24.000, 6353),
            (25.000, 6167),
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