# Handles the logic for event logging
import sqlite3
from typing import List
import os

# Define paths to connect to the SQLite database
DB_PATH = os.path.join(os.path.dirname(__file__), "mice_squat.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Connect to the SQLite database
conn = sqlite3.connect(DB_PATH)

def log_event(str: event_type, float: distance):
    """
    Logs an event with the given type and data.
    
    Args:
        event_type (str): The type of the event.
        distance: distance of lift (if lift event)
    """

    if event_type == "lift":
        # Logic for logging weight lift event
        # 1. Convert distance to a string
        # 2. Insert data into database via rsync
        pass
    elif event_type == "pellet_taken":
        # Logic for logging pellet taken event
        # Insert data into database via rsync
        pass