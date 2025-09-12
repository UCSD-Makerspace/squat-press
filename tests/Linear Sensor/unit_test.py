import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv

SAMPLE_INTERVAL = 0.1  # seconds
STEPS_PER_2_5CM = 915  # steps for 2.5cm motion

def read_sensor(sensor):
    pos = sensor.get_position()
    if isinstance(pos, tuple):
        raw_value, _ = pos
    else:
        raw_value = pos
    if raw_value is not None:
        return sensor.interpolate(raw_value)
    return None

def main():
    # Motor setup
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)

    # Sensor setup
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    # CSV setup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm"])

    # Live plot setup
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    times, positions = [], []
    line, = ax.plot([], [], 'b-', lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Motor Linear Sensor Monitoring")
    ax.grid(True)
    start_time = time.time()

    dir = -1
    try:
        while True:
            dir = -dir
            thread, _ = motor.rotate_degrees_threaded(dir * STEPS_PER_2_5CM, 0)
            thread.join()

            # Record sensor for ~1 second
            for _ in range(int(1 / SAMPLE_INTERVAL)):
                mm_value = read_sensor(sensor)
                if mm_value is not None:
                    elapsed = time.time() - start_time
                    times.append(elapsed)
                    positions.append(mm_value)

                    # Write full-resolution CSV
                    csv_writer.writerow([elapsed, mm_value])
                    csv_file.flush()

                    # Live plot: keep only last 200 points
                    times_live = times[-200:]
                    positions_live = positions[-200:]
                    line.set_xdata(times_live)
                    line.set_ydata(positions_live)
                    ax.relim()
                    ax.autoscale_view()
                    plt.pause(0.01)

                time.sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        # Close CSV
        csv_file.close()

        # Save live plot (last ~200 points)
        plot_filename_live = f"sensor_plot_{timestamp}.png"
        fig.savefig(plot_filename_live)

        # Save full timeline plot (downsampled)
        downsample_factor = max(1, len(times) // 10000)  # max 10k points
        times_ds = times[::downsample_factor]
        positions_ds = positions[::downsample_factor]

        fig_full, ax_full = plt.subplots(figsize=(14, 6))
        ax_full.plot(times_ds, positions_ds, 'b-')
        ax_full.set_xlabel("Time (s)")
        ax_full.set_ylabel("Position (mm)")
        ax_full.set_title("Full Linear Sensor Timeline (downsampled)")
        ax_full.grid(True)
        plot_filename_full = f"full_sensor_plot_{timestamp}.png"
        fig_full.savefig(plot_filename_full)
        plt.ioff()
        plt.show()

        print(f"Data saved to sensor_log_{timestamp}.csv")
        print(f"Live plot saved to {plot_filename_live}")
        print(f"Full timeline plot saved to {plot_filename_full}")

if __name__ == "__main__":
    main()
