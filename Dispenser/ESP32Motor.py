import serial
import time

class ESP32Motor:
    def __init__(self, port = "/dev/ttyACM1", baudrate = 115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Connected to ESP32 motor controller on {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"Failed to connect to ESP32 motor controller: {e}")
            return False
        
    def dispense(self, dispense) -> bool:
        if not self.ser or not self.ser.is_open:
            print("Not connected to ESP32 motor controller!")
            return False

        command = f"{dispense}\n"
        self.ser.write(command.encode("ascii"))
        self.ser.flush()

        response = self.ser.readline().decode("ascii").strip()
        if response:
            print(f"ESP32 motor response: {response}")
            return True
        
        return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Disconnected from ESP32 motor controller")
