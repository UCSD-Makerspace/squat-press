import csv
import logging
import os
import queue

from events import EventType

write_path = "home/pi/mice_squat/logs/event_log.csv"
os.makedirs(os.path.dirname(write_path), exist_ok=True)
class EventManager:
    def __init__(self, event_queue, dispenser):
        self.q = event_queue
        self.dispenser = dispenser
        self.ready_to_dispense = True

    def run(self):
        while True:
            try:
                evt, payload, t = self.q.get(timeout=1)
            except queue.Empty:
                continue  # just loop again if no events

            self.log_event(evt, payload, t)
            if evt == EventType.LIFT_DETECTED:
                logging.info("Lift detected, dispensing pellet...")
                self.dispenser.dispense_pellet()
                self.ready_to_dispense = False

            elif evt == EventType.PELLET_TAKEN:
                logging.info("Pellet taken, ready for next lift.")
                self.ready_to_dispense = True

    def log_event(self, evt, payload, t):
        logging.info(f"Event: {evt}, Payload: {payload}, Time: {t}")
        with open(write_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([evt, payload, t])
