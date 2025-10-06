import threading
import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv

SAMPLE_INTERVAL = 0.02  # 50 Hz
STEPS_PER_MM = 36


def check_mm_value(sensor):
    """Return (interpolated mm, raw decimal value)"""
    raw_val = sensor.send_command('F')
    if raw_val:
        try:
            decimal_value = int(raw_val.split()[0], 16)
            mm = sensor.interpolate(decimal_value)
            return mm, decimal_value
        except Exception as e:
            print(f"Parse error: {e}, raw={raw_val}")
    return None, None


def sensor_thread_func(sensor, csv_writer, times, positions, lock, start_time, stop_event):
    """Background thread: continuously reads sensor and updates plot data"""
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot([], [], 'b-', lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Motor Linear Sensor Monitoring (Live)")
    ax.grid(True)

    while not stop_event.is_set():
        mm_value, raw_val = check_mm_value(sensor)
        if mm_value is not None:
            elapsed = time.time() - start_time
            with lock:
                times.append(elapsed)
                positions.append(mm_value)

            # Write CSV entry
            csv_writer.writerow([elapsed, mm_value, raw_val])

            # Live plot update (keep last 200 points)
            with lock:
                times_live = times[-200:]
                positions_live = positions[-200:]
            line.set_xdata(times_live)
            line.set_ydata(positions_live)
            ax.relim()
            ax.autoscale_view()
            plt.pause(0.001)

        time.sleep(SAMPLE_INTERVAL)

    print("Sensor thread stopped")
    plt.ioff()
    plt.show()


def main():
    motor = tmc2209.TMC2209()
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm", "raw_value"])

    times, positions = [], []
    lock = threading.Lock()
    stop_event = threading.Event()
    start_time = time.time()

    # Start sensor sampling thread
    thread = threading.Thread(
        target=sensor_thread_func,
        args=(sensor, csv_writer, times, positions, lock, start_time, stop_event),
        daemon=True
    )
    thread.start()

    try:
        current_direction = tmc2209.Direction.CLOCKWISE
        total_steps_going_up = 0

        velocities = [20, 33, 66, 50, 57, 100]  # mm/s
        time_frames = [0.05, 0.08, 0.11, 0.15, 0.22, 0.24]  # s

        while True:
            # Switch direction each cycle
            current_direction = (
                tmc2209.Direction.COUNTERCLOCKWISE
                if current_direction == tmc2209.Direction.CLOCKWISE
                else tmc2209.Direction.CLOCKWISE
            )
            motor.set_direction(current_direction)

            if current_direction == tmc2209.Direction.CLOCKWISE:
                total_steps = 0
                for velocity, time_frame in zip(velocities, time_frames):
                    steps = int(time_frame * velocity * STEPS_PER_MM)
                    delay = 1 / (2 * velocity * STEPS_PER_MM)
                    print(f"[UP] {velocity} mm/s for {time_frame}s -> {steps} steps")
                    motor.step(steps, delay)
                    total_steps += steps
                total_steps_going_up = total_steps
                print(f"Total up steps: {total_steps_going_up}")

            else:
                delay = 1 / (2 * 20 * STEPS_PER_MM)  # constant 20 mm/s down
                print(f"[DOWN] {total_steps_going_up} steps at 20 mm/s")
                motor.step(total_steps_going_up, delay)

            time.sleep(1.0)  # small rest before next direction

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        stop_event.set()
        thread.join()
        csv_file.close()

        # Downsample full data for saving
        with lock:
            downsample_factor = max(1, len(times) // 10000)
            times_ds = times[::downsample_factor]
            positions_ds = positions[::downsample_factor]

        fig_full, ax_full = plt.subplots(figsize=(14, 6))
        ax_full.plot(times_ds, positions_ds, 'b-')
        ax_full.set_xlabel("Time (s)")
        ax_full.set_ylabel("Position (mm)")
        ax_full.set_title("Full Linear Sensor Timeline (Downsampled)")
        ax_full.grid(True)
        fig_full.savefig(f"full_sensor_plot_{timestamp}.png")

        print(f"Data saved to sensor_log_{timestamp}.csv")


if __name__ == "__main__":
    main()
