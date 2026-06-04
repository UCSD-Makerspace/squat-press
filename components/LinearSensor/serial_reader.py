import serial
import time
from datetime import datetime

# Calibration run: 2026-06-04
CALIBRATION_TABLE = [
    (0.000, 10611), (1.000, 10462), (2.000, 10294), (3.000, 10118),
    (4.000,  9987), (5.000,  9849), (6.000,  9652), (7.000,  9567),
    (8.000,  9462), (9.000,  9216),(10.000,  8999),(11.000,  8744),
    (12.000, 8475),(13.000,  8307),(14.000,  8126),(15.000,  7962),
    (16.000, 7797),(17.000,  7648),(18.000,  7447),(19.000,  7295),
    (20.000, 7070),(21.000,  6880),(22.000,  6710),(23.000,  6499),
    (24.000, 6300),(25.000,  6146),
]

def interpolate(raw: int) -> float | None:
    """Convert a raw ADC value to millimetres via linear interpolation."""
    t = CALIBRATION_TABLE
    if raw >= t[0][1]:  return t[0][0]
    if raw <= t[-1][1]: return t[-1][0]
    for i in range(len(t) - 1):
        mm1, r1 = t[i]; mm2, r2 = t[i + 1]
        if r2 <= raw <= r1:
            return mm1 + (raw - r1) / (r2 - r1) * (mm2 - mm1)
    return None


class LinearSensorReader:
    def __init__(self, port, baudrate=115200):
        self.port     = port
        self.baudrate = baudrate
        self.ser      = None
        self.running  = False

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

    def send_command(self, command: str) -> str | None:
        if not self.ser or not self.ser.is_open:
            print("Not connected!")
            return None
        try:
            self.ser.write(command.encode('ascii'))
            return self.ser.readline().decode('ascii').strip()
        except Exception as e:
            print(f"Command error: {e}")
            return None

    def get_position(self) -> float | None:
        response = self.send_command('F')
        if response:
            try:
                return interpolate(int(response.split()[0], 16))
            except Exception as e:
                print(f"Parse error: {e}, raw={response}")
        return None

    def get_status(self)      -> str | None: return self.send_command('G')
    def get_device_info(self) -> str | None: return self.send_command('A')
