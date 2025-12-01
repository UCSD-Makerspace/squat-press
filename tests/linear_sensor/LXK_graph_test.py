import serial
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from datetime import datetime

# Calibration table (mm, raw)
calibration_table = [
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

# Prepare interpolation function
raw_vals = [r for _, r in calibration_table]
mm_vals = [mm for mm, _ in calibration_table]
interp_func = interp1d(raw_vals, mm_vals, kind='linear', fill_value='extrapolate')

# Sensor config
PORT = 'COM3'
BAUDRATE = 115200
SAMPLE_INTERVAL = 0.1  # 20 Hz

def get_sensor_reading(ser):
    try:
        ser.write('F'.encode('ascii'))
        response = ser.readline().decode('ascii').strip()
        if response:
            hex_part = response.split()[0]
            return int(hex_part, 16)
    except:
        return None
    return None

def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
        print(f"Connected to {PORT} at {BAUDRATE} baud")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    times, positions = [], []
    line, = ax.plot([], [], 'b-', lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Real-Time Linear Sensor Reading")
    ax.grid(True)

    start_time = time.time()
    try:
        while True:
            raw = get_sensor_reading(ser)
            if raw is not None:
                mm_value = float(interp_func(raw))
                times.append(time.time() - start_time)
                positions.append(mm_value)

                # Keep only the last 200 samples for smoother plotting
                if len(times) > 200:
                    times.pop(0)
                    positions.pop(0)

                line.set_xdata(times)
                line.set_ydata(positions)
                ax.relim()
                ax.autoscale_view()
                plt.pause(0.01)
            else:
                print("Warning: Failed to read sensor")

            time.sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        ser.close()
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()
