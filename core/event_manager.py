import logging
import queue

from events import EventType

class EventManager:
    def __init__(self, event_queue, dispenser):
        self.q = event_queue
        self.dispenser = dispenser
        self.ready_to_dispense = True

    def run(self):
        while True:
            evt, payload, t = self.q.get()
            if evt == EventType.LIFT_DETECTED and self.ready_to_dispense:
                logging.info("Lift detected, dispensing pellet...")
                self.dispenser.dispense()
                self.ready_to_dispense = False

            elif evt == EventType.PELLET_TAKEN:
                logging.info("Pellet taken, ready for next lift.")
                self.ready_to_dispense = True
