import Dispenser.TMC2209.tmc2209 as tmc2209
import lx3302a.SENTReader.serial_reader as serial_reader
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from time import sleep, time

### Calibration table ###
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
interp_func = interp1d(raw_vals, mm_vals, kind="linear", fill_value="extrapolate")

SAMPLE_INTERVAL = 0.1

def main():
    # Motor setup
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)

    # Sensor setup
    p = serial_reader.LinearSensorReader("/dev/ttyACM0", 115200)
    if not p.connect():
        raise Exception("Failed to connect to linear sensor")

    # Plot setup
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    times, positions = [], []
    line, = ax.plot([], [], "b-", lw=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (mm)")
    ax.set_title("Real-Time Linear Sensor Reading During Motor Motion")
    ax.grid(True)

    start_time = time()
    dir = 1

    try:
        while True:
            # Move motor
            dir = -dir
            dist = dir * 910
            thread, _ = motor.rotate_degrees_threaded(dist, 0)
            print(f"Rotating {dist} degrees...")
            thread.join()
            print("Rotation complete.")
            print(f"Current position: {motor.position:.2f} revolutions")

            # Gather sensor data during each pause
            for _ in range(int(1 / SAMPLE_INTERVAL)):  # sample for ~1s
                raw = p.get_raw_value()  # Replace with actual method name if different
                if raw is not None:
                    mm_value = float(interp_func(raw))
                    times.append(time() - start_time)
                    positions.append(mm_value)

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
                sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()
