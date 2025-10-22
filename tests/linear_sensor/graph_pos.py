import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv
from typing import Optional

def check_mm_value(sensor: serial_reader.LinearSensorReader, last_val: Optional[float], last_raw_val: Optional[float]):
    """Return (interpolated mm, raw decimal value)"""
    raw_val = sensor.send_command('F')
    if raw_val:
        try:
            decimal_value = int(raw_val.split()[0], 16)
            mm = sensor.interpolate(decimal_value)
            return mm, decimal_value
        except Exception as e:
            print(f"Parse error: {e}, raw={raw_val}")
    return last_val, last_raw_val

def main():
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm", "raw_value"])

    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    times, positions = [], []
    line, = ax.plot([], [], 'b-', lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Motor Linear Sensor Monitoring")
    ax.grid(True)
    start_time = time.time()

    mm_value = None
    raw_val = None

    try:
        while True:
            mm_value, raw_val = check_mm_value(sensor, mm_value, raw_val)

            if mm_value is not None:
                elapsed = time.time() - start_time
                times.append(elapsed)
                positions.append(mm_value)

                csv_writer.writerow([elapsed, mm_value, raw_val])
                csv_file.flush()
                
                times_live = times[-200:]
                positions_live = positions[-200:]
                line.set_xdata(times_live)
                line.set_ydata(positions_live)
                ax.relim()
                ax.autoscale_view()
                plt.pause(0.01)
           

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
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