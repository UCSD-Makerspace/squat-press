import time
import matplotlib.pyplot as plt
from PhotoInterruptor import PhotoInterruptor

RECORD_TIME = 10

def main():
    LTC = PhotoInterruptor()
    readings = []

    start = time.time()
    while time.time() - start < RECORD_TIME: 
        LTC.update()
        timestamp = time.time() - start
        readings.append((timestamp, LTC.get_data_percent(), LTC.get_detected()))
        time.sleep(0.05)

    # Separate into arrays
    times = [r[0] for r in readings]
    values = [r[1] for r in readings]
    detected_flags = [r[2] for r in readings]

    plt.figure(figsize=(10, 4))
    plt.plot(times, values, label="Data Percent")
    plt.axhline(y=LTC.threshold, color='r', linestyle='--', label="Threshold")

    # Shade detected regions
    for i in range(len(times)-1):
        if detected_flags[i]:
            plt.axvspan(times[i], times[i+1], color='green', alpha=0.3)

    plt.xlabel("Time (s)")
    plt.ylabel("Data Percent")
    plt.title("PhotoInterruptor ADC Data")
    plt.legend()
    plt.show()

if __name__ == "__main__":
    main()
