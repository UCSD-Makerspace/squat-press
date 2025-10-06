import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from datetime import datetime
import time
import csv
import os

SAMPLE_INTERVAL = 0.1
STEPS_PER_MM = 290  # for waveform

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


def step_motor_with_recording(motor, sensor, direction, velocities, time_frames,
                              times, positions, start_time, csv_writer, csv_file, mm_value, since_last_mm):
    """Perform stepping for a given direction and record sensor data."""
    total_steps = 0

    for velocity, time_frame in zip(velocities, time_frames):
        print(f"[{direction.name}] {velocity} mm/s for {time_frame}s")
        steps = int(time_frame * velocity * STEPS_PER_MM)
        freq = velocity * STEPS_PER_MM
        print(f"  -> {steps} steps @ freq {freq:.1f}Hz for {steps / freq:.3f}s")

        motor.step_waveform(steps, freq)
        total_steps += steps

        # Record data point
        mm_value, since_last_mm, raw_val = check_mm_value(sensor, mm_value, since_last_mm)
        if mm_value is not None:
            elapsed = time.time() - start_time
            times.append(elapsed)
            positions.append(mm_value)
            csv_writer.writerow([elapsed, mm_value, raw_val])
            csv_file.flush()

    print(f"Total {direction.name} steps: {total_steps}")
    return total_steps, mm_value, since_last_mm


def update_plot(ax, line, times, positions):
    """Refresh live matplotlib plot."""
    times_live = times[-200:]
    positions_live = positions[-200:]
    line.set_xdata(times_live)
    line.set_ydata(positions_live)
    ax.relim()
    ax.autoscale_view()
    plt.pause(0.01)


def run_motor_cycle(motor, sensor, pos_velocities, pos_time_frames,
                    neg_velocities, neg_time_frames, times, positions,
                    start_time, csv_writer, csv_file):
    """Perform one full up/down cycle."""
    mm_value = None
    since_last_mm = 0.0
    total_steps_going_up = 0

    # Up
    motor.set_direction(tmc2209.Direction.COUNTERCLOCKWISE)
    total_steps_going_up, mm_value, since_last_mm = step_motor_with_recording(
        motor, sensor, tmc2209.Direction.COUNTERCLOCKWISE,
        pos_velocities, pos_time_frames,
        times, positions, start_time, csv_writer, csv_file, mm_value, since_last_mm
    )

    # Down
    motor.set_direction(tmc2209.Direction.CLOCKWISE)
    print(f"[DOWN] {total_steps_going_up} steps at 20 mm/s")
    motor.step_waveform(total_steps_going_up, 20 * STEPS_PER_MM)
    return mm_value, since_last_mm


def main():
    motor = tmc2209.TMC2209()
    sensor = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not sensor.connect():
        raise Exception("Failed to connect to linear sensor")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = open(f"sensor_log_{timestamp}.csv", "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time_s", "position_mm", "raw_value"])

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

    # Load velocity config
    base_dir = os.path.dirname(__file__)
    pos_path = os.path.join(base_dir, 'pos_velocity_config.csv')
    neg_path = os.path.join(base_dir, 'neg_velocity_config.csv')

    pos_velocities, pos_time_frames = [], []
    with open(pos_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pos_velocities.append(float(row['velocities']))
            pos_time_frames.append(float(row['time_frames']))

    neg_velocities, neg_time_frames = [], []
    with open(neg_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            neg_velocities.append(float(row['velocities']))
            neg_time_frames.append(float(row['time_frames']))

    try:
        while True:
            mm_value, since_last_mm = run_motor_cycle(
                motor, sensor,
                pos_velocities, pos_time_frames,
                neg_velocities, neg_time_frames,
                times, positions,
                start_time, csv_writer, csv_file
            )
            update_plot(ax, line, times, positions)

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        csv_file.close()
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()