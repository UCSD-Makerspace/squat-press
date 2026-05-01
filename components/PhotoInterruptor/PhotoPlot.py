import time
import matplotlib
matplotlib.use("Agg")  # Use non-GUI backend
import matplotlib.pyplot as plt
from PhotoInterruptor import PhotoInterruptor

def main():
    LTC = PhotoInterruptor()
    readings = []

    start = time.time()
    capture_time = 10  # seconds

    while time.time() - start < capture_time:
        LTC.update()
        timestamp = time.time() - start
        readings.append((timestamp, LTC.get_data_percent(), LTC.get_detected()))
        time.sleep(0.05)  # 20 Hz sampling

    # Separate into arrays
    times = [r[0] for r in readings]
    values = [r[1] for r in readings]
    detected_flags = [r[2] for r in readings]

    # Plot
    plt.figure(figsize=(10, 4))
    plt.plot(times, values, label="Data Percent")
    plt.axhline(y=LTC.threshold, color='r', linestyle='--', label="Threshold")

    for i in range(len(times) - 1):
        if detected_flags[i]:
            plt.axvspan(times[i], times[i + 1], color='green', alpha=0.3)

    plt.xlabel("Time (s)")
    plt.ylabel("Data Percent")
    plt.title("PhotoInterruptor ADC Data")
    plt.legend()

    # Save image instead of showing
    plt.savefig("photo_plot.png", dpi=150)
    print("Plot saved as photo_plot.png")

if __name__ == "__main__":
    main()
