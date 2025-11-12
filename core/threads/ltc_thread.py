import threading, time
from events import EventType

class LTCThread(threading.Thread):
    def __init__(self, LTC, event_queue):
        super().__init__(daemon=True)
        self.LTC = LTC
        self.queue = event_queue
        self.last_state = self.LTC.get_detected()

    def run(self):
        while True:
            current_state = self.LTC.get_detected()
            if current_state != self.last_state:
                self.last_state = current_state
                event_type = EventType.PELLET_DISPENSED if current_state else EventType.PELLET_TAKEN
                self.queue.put((event_type, current_state, time.time()))
            time.sleep(0.1)

    