import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from datetime import datetime
import time
import csv

# ---------------- Calibration Table ---------------- #
calibration_table = [
    (0.000, 10575), (0.635, 10495), (1.270, 10420), (1.905, 10335),
    (2.540, 10245), (3.175, 10155), (3.810, 10055), (4.445, 9950),
    (5.080, 9840), (5.715, 9735), (6.350, 9650), (6.985, 9585),
    (7.620, 9520), (8.255, 9455), (8.890, 9305), (9.525, 9145),
    (10.160, 8995), (10.795, 8825), (11.430, 8680), (12.065, 8540),
    (12.700, 8395), (13.335, 8285), (13.970, 8185), (14.605, 8080),
    (15.240, 7980), (15.875, 7885), (16.510, 7785), (17.145, 7685),
    (17.780, 7575), (18.415, 7455), (19.050, 7355), (19.685, 7215),
    (20.320, 7100), (20.955, 6985), (21.590, 6855), (22.225, 6810),
]
raw_vals = [r for _, r in calibration_table]
mm_vals = [mm for mm, _ in calibration_table]
interp_func = interp1d(raw_vals, mm_vals, kind='linear', fill_value='extrapolate')

# ---------------- Config ---------------- #
SAMPLE_INTERVAL = 0.1  # seconds

# ---------------- Helper ---------------- #
def read_sensor(sensor):
    try:
        raw = sensor.get_raw_value()  # adjust method name if different
        if raw is not None:
            return float(interp_func(raw))
    except:
        pass
    return None

# ---------------- Main ---------------- #
def main():
    # Motor setup
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)

    # Sensor setup
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    # CSV logging setup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm"])

    # Plot setup
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    times, positions = [], []
    line, = ax.plot([], [], 'b-', lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Motor Linear Sensor Monitoring")
    ax.grid(True)
    start_time = time.time()

    # Motion loop: up 2.5cm, down 2.5cm
    # Compute steps for 2.5cm based on your calibration: adjust as needed
    # Example: dist_degrees = 2.5cm / 139.75mm * 10000steps -> convert to degrees for motor
    steps_per_2_5cm = 915 # Found from calibration (this is in steps)  

    dir = -1
    try:
        while True:
            dir = -dir
            thread, _ = motor.rotate_degrees_threaded(steps_per_2_5cm, 0)
            # print(f"Rotating {dir * steps_per_2_5cm} degrees...")
            thread.join()
            print(f"Rotation complete. Motor position: {motor.position:.2f} revs")

            # During pause, record sensor for ~1s
            for _ in range(int(1 / SAMPLE_INTERVAL)):
                mm_value = read_sensor(sensor)
                if mm_value is not None:
                    elapsed = time.time() - start_time
                    times.append(elapsed)
                    positions.append(mm_value)

                    csv_writer.writerow([elapsed, mm_value])
                    csv_file.flush()

                    if len(times) > 200:
                        times.pop(0)
                        positions.pop(0)

                    line.set_xdata(times)
                    line.set_ydata(positions)
                    ax.relim()
                    ax.autoscale_view()
                    plt.pause(0.01)
                time.sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        csv_file.close()
        plot_filename = f"sensor_plot_{timestamp}.png"
        fig.savefig(plot_filename)
        plt.ioff()
        plt.show()
        print(f"Data saved to sensor_log_{timestamp}.csv")
        print(f"Plot saved to {plot_filename}")

if __name__ == "__main__":
    main()
