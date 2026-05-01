"""
This module defines event types used in the event management system.
"""

from enum import Enum, auto
class EventType(Enum):
    """
    Enumeration of different event types.
    """
    LIFT_DETECTED = auto()
    LIFT_COMPLETED = auto()
    PELLET_DISPENSED = auto()
    PELLET_DETECTED = auto()
    PELLET_TAKEN = auto()
