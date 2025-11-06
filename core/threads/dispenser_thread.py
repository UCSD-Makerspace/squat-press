import threading, time
from rotate import dispense

class DispenserThread(threading.Thread):
    def __init__(self, motor, event_queue):
        super().__init__(daemon=True)
        self.motor = motor
        self.queue = event_queue

    def dispense(self):
        self.motor.dispense()
        self.queue.put((EventType.DISPENSEDONE, None, time.time()))