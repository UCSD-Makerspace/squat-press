import csv
import logging

from events import EventType

write_path = "home/pi/mice_squat/logs/event_log.csv"
class EventManager:
    def __init__(self, event_queue, dispenser):
        self.q = event_queue
        self.dispenser = dispenser
        self.ready_to_dispense = True

    def run(self):
        while True:
            evt, payload, time = self.q.get()
            self.log_event(evt, payload, time)
            if evt == EventType.LIFT_DETECTED and self.ready_to_dispense:
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
