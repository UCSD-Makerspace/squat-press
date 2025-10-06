import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv

SAMPLE_INTERVAL = 0.1
# STEPS_PER_2_5CM = 915
STEPS_PER_MM = 36

def check_mm_value(sensor, mm_value, since_last_mm):
    """Return (interpolated mm, since_last_mm, raw decimal value)"""
    raw_val = sensor.send_command('F')
    if raw_val:
        try:
            decimal_value = int(raw_val.split()[0], 16)
            mm = sensor.interpolate(decimal_value)
            return mm, 0.0, decimal_value
        except Exception as e:
            print(f"Parse error: {e}, raw={raw_val}")
    return mm_value, since_last_mm + SAMPLE_INTERVAL, None

def main():
    motor = tmc2209.TMC2209()
    # motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    
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
    since_last_mm = 0.0
    current_direction = tmc2209.Direction.CLOCKWISE
    total_steps_going_up = 0

    try:
        while True:
            if current_direction == tmc2209.Direction.COUNTERCLOCKWISE:
                current_direction = tmc2209.Direction.CLOCKWISE

            else:
                current_direction = tmc2209.Direction.COUNTERCLOCKWISE
            motor.set_direction(current_direction)
            
            if current_direction == tmc2209.Direction.CLOCKWISE:
                total_steps = 0
                motor.set_direction(current_direction)
                velocities = [0.2, 0.33, 0.66, 0.5, 0.57, 1] # mm per 10 ms
                time_frames = [0.05, 0.08, 0.11, 0.15, 0.22, 0.24] # seconds
                for velocity in velocities:
                    print(f"Attempting {velocity}")
                    steps_per_10_ms = int(velocity * STEPS_PER_MM)
                    s_per_half_step = time_frames * 100 / steps_per_10_ms / 2
                    print(f"Stepping {steps_per_10_ms} steps, with {s_per_half_step} delays")
                    motor.step(steps_per_10_ms, s_per_half_step)
                    total_steps += steps_per_10_ms
                print(f"Stepped {total_steps} in total")
                total_steps_going_up = total_steps
            
            else:
                motor.step(total_steps_going_up)
            

            # During pause, record sensor for ~1s
            for _ in range(int(1 / SAMPLE_INTERVAL)):
                mm_value, since_last_mm, raw_val = check_mm_value(sensor, mm_value, since_last_mm)

                if mm_value is not None:
                    elapsed = time.time() - start_time
                    times.append(elapsed)
                    positions.append(mm_value)

                    # Write full-resolution CSV with raw value
                    csv_writer.writerow([elapsed, mm_value, raw_val])
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