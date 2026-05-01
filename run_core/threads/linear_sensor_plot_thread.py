import threading
import matplotlib.pyplot as plt
import time
from collections import deque

class PlotThread(threading.Thread):
    def __init__(self, data_queue, sample_window=200):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.sample_window = sample_window
        self.times = deque(maxlen=sample_window)
        self.values = deque(maxlen=sample_window)
        self.start_time = time.time()

    def run(self):
        plt.ion()
        fig, ax = plt.subplots(figsize=(10, 6))
        line, = ax.plot([], [], lw=2)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position (mm)")
        ax.set_title("Real-Time Linear Sensor Reading")
        ax.grid(True)

        while True:
            # Pull all available values
            while not self.data_queue.empty():
                mm_value = self.data_queue.get()
                self.times.append(time.time() - self.start_time)
                self.values.append(mm_value)

            # Update plot
            line.set_xdata(list(self.times))
            line.set_ydata(list(self.values))
            ax.relim()
            ax.autoscale_view()
            plt.pause(0.01)

            time.sleep(0.01)
