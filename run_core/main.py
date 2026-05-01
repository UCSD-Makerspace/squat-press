import queue
from collections import deque

from run_core.threads.dispenser_thread import DispenserThread
from run_core.threads.linear_sensor_thread import LinearSensorThread
from run_core.threads.ltc_thread import LTCThread
from run_core.threads.linear_sensor_plot_thread import PlotThread
from event_manager import EventManager

from utils import init_hardware, init_pi, check_all_hardware

def main():
    pi, linear_sensor, motor = None, None, None

    pi = init_pi()
    linear_sensor, ltc, motor = init_hardware(pi)
    check_all_hardware(pi, ltc, motor)

    event_queue = queue.Queue()
    plot_queue = queue.Queue()

    linear_thread = LinearSensorThread(linear_sensor, event_queue, 
                        plot_queue, mm_threshold=10, recent_lifts=deque())
    ltc_thread = LTCThread(ltc, event_queue)
    dispenser_thread = DispenserThread(motor, event_queue)
    plot_thread = PlotThread(plot_queue, sample_window=200)

    linear_thread.start()
    ltc_thread.start()
    dispenser_thread.start()
    plot_thread.start()
    
    # Main controller
    manager = EventManager(event_queue, dispenser_thread)
    manager.run()

if __name__ == "__main__":
    main()