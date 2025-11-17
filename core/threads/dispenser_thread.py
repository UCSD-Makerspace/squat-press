import threading, time
from events import EventType

class DispenserThread(threading.Thread):
    def __init__(self, motor, event_queue):
        super().__init__(daemon=True)
        self.motor = motor
        self.queue = event_queue

    def dispense_pellet(self):
        self.motor.dispense("d")
        self.queue.put((EventType.PELLET_DISPENSED, None, time.time()))