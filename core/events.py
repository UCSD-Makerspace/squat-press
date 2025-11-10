from enum import Enum, auto
import queue

class EventType(Enum):
    LIFT_DETECTED = auto()
    LIFT_COMPLETED = auto()
    PELLET_DISPENSED = auto()
    PELLET_TAKEN = auto()

event_queue = queue.Queue()