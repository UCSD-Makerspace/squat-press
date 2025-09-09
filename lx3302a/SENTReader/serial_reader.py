import serial
import time
from datetime import datetime

class LinearSensorReader:
    def __init__(self, port='COM3', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

        self.calibration_table = [
        (0.000, 10575),
        (0.635, 10495),
        (1.270, 10420),
        (1.905, 10335),
        (2.540, 10245),
        (3.175, 10155),
        (3.810, 10055),
        (4.445, 9950),
        (5.080, 9840),
        (5.715, 9735),
        (6.350, 9650),
        (6.985, 9585),
        (7.620, 9520),
        (8.255, 9455),
        (8.890, 9305),
        (9.525, 9145),
        (10.160, 8995),
        (10.795, 8825),
        (11.430, 8680),
        (12.065, 8540),
        (12.700, 8395),
        (13.335, 8285),
        (13.970, 8185),
        (14.605, 8080),
        (15.240, 7980),
        (15.875, 7885),
        (16.510, 7785),
        (17.145, 7685),
        (17.780, 7575),
        (18.415, 7455),
        (19.050, 7355),
        (19.685, 7215),
        (20.320, 7100),
        (20.955, 6985),
        (21.590, 6855),
        (22.225, 6810),
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

        return None

    def get_status(self):
        return self.send_command('G')

    def get_device_info(self):
        return self.send_command('A')