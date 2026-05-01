import serial
import time
from datetime import datetime
import csv

class CalibrationGenerator:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.calibration_data = []
        self.sample_buffer = []
        self.samples_per_point = 50

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

    def get_raw_value(self):
        """Get raw sensor value using 'F' command"""
        response = self.send_command('F')
        if response:
            try:
                hex_part = response.split()[0]
                decimal_value = int(hex_part, 16)
                return decimal_value
            except:
                return None
        return None

    def collect_samples(self, num_samples):
        """Collect and display samples in real-time"""
        self.sample_buffer = []
        print(f"\nCollecting {num_samples} samples...")
        print("Raw values: ", end="", flush=True)
        
        for i in range(num_samples):
            raw_value = self.get_raw_value()
            if raw_value is not None:
                self.sample_buffer.append(raw_value)
                print(f"{raw_value} ", end="", flush=True)
                if (i + 1) % 10 == 0:
                    print(f"[{i + 1}/{num_samples}] ", end="", flush=True)
            time.sleep(0.01)  # Small delay between samples
        
        print()  # New line after samples
        
        if self.sample_buffer:
            avg_value = sum(self.sample_buffer) / len(self.sample_buffer)
            min_value = min(self.sample_buffer)
            max_value = max(self.sample_buffer)
            print(f"Average: {avg_value:.1f} | Min: {min_value} | Max: {max_value} | Std Dev: {self._calc_stddev():.2f}")
            return avg_value
        return None

    def _calc_stddev(self):
        """Calculate standard deviation of samples"""
        if len(self.sample_buffer) < 2:
            return 0
        avg = sum(self.sample_buffer) / len(self.sample_buffer)
        variance = sum((x - avg) ** 2 for x in self.sample_buffer) / len(self.sample_buffer)
        return variance ** 0.5

    def calibrate(self, max_mm=25):
        """Run the calibration process"""
        print(f"\n{'='*60}")
        print(f"LINEAR SENSOR CALIBRATION GENERATOR")
        print(f"Samples per point: {self.samples_per_point}")
        print(f"Range: 0mm to {max_mm}mm")
        print(f"{'='*60}\n")
        
        input("Press Enter when ready to start calibration...")
        
        for mm in range(max_mm + 1):
            input(f"\nPosition sensor at {mm}mm, then press SPACE to collect {self.samples_per_point} samples...")
            
            avg_raw = self.collect_samples(self.samples_per_point)
            
            if avg_raw is not None:
                self.calibration_data.append((mm, avg_raw))
                print(f"✓ Recorded: {mm}mm = {avg_raw:.1f} raw")
            else:
                print(f"✗ Failed to collect samples at {mm}mm. Retrying...")
                mm -= 1  # Retry this position
        
        return True

    def save_calibration(self, filename="calibration_data.csv"):
        """Save calibration data to CSV"""
        if not self.calibration_data:
            print("No calibration data to save!")
            return False
        
        try:
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['mm', 'raw_value'])
                for mm, raw in self.calibration_data:
                    writer.writerow([mm, f'{raw:.1f}'])
            print(f"\nCalibration data saved to: {filename}")
            return True
        except Exception as e:
            print(f"Error saving CSV: {e}")
            return False

    def generate_python_table(self, filename="calibration_table.py"):
        """Generate Python code for the calibration table"""
        if not self.calibration_data:
            print("No calibration data to generate table!")
            return False
        
        try:
            with open(filename, 'w') as f:
                f.write("# Auto-generated calibration table\n")
                f.write("# Generated on: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                f.write("# Samples per point: {}\n\n".format(self.samples_per_point))
                f.write("calibration_table = [\n")
                
                # Sort by mm value to ensure correct order
                sorted_data = sorted(self.calibration_data, key=lambda x: x[0])
                
                for mm, raw in sorted_data:
                    f.write(f"    ({mm:.3f}, {raw:.0f}),\n")
                
                f.write("]\n")
            
            print(f"Python calibration table saved to: {filename}")
            return True
        except Exception as e:
            print(f"Error generating Python table: {e}")
            return False

    def display_calibration(self):
        """Display the collected calibration data"""
        if not self.calibration_data:
            print("No calibration data to display!")
            return
        
        print(f"\n{'='*50}")
        print(f"CALIBRATION TABLE")
        print(f"{'='*50}")
        print(f"{'mm':<8} {'Raw Value':<15}")
        print(f"{'-'*50}")
        
        sorted_data = sorted(self.calibration_data, key=lambda x: x[0])
        for mm, raw in sorted_data:
            print(f"{mm:<8.1f} {raw:<15.1f}")
        
        print(f"{'='*50}\n")

if __name__ == "__main__":
    # Configuration
    PORT = "/dev/ttyACM1"
    BAUDRATE = 115200
    MAX_MM = 25
    SAMPLES_PER_POINT = 50
    
    cal_gen = CalibrationGenerator(PORT, BAUDRATE)
    cal_gen.samples_per_point = SAMPLES_PER_POINT
    
    if cal_gen.connect():
        try:
            # Run calibration
            cal_gen.calibrate(max_mm=MAX_MM)
            
            # Display results
            cal_gen.display_calibration()
            
            # Save outputs
            cal_gen.save_calibration("calibration_data.csv")
            cal_gen.generate_python_table("calibration_table.py")
            
            print("\nCalibration complete!")
            print("Files created:")
            print("  - calibration_data.csv (for backup/analysis)")
            print("  - calibration_table.py (Python tuple format)")
            
        except KeyboardInterrupt:
            print("\n\nCalibration interrupted by user")
        finally:
            cal_gen.disconnect()
    else:
        print("Failed to connect to sensor")