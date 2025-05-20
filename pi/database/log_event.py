# Handles the logic for event logging
import sqlite3
from typing import Optional
import os

# =========== Configuration ===========
DB_PATH = os.path.join(os.path.dirname(__file__), "mice_squat.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Connect to the SQLite database
conn = sqlite3.connect(DB_PATH)
if conn:
    print("Connected to the database successfully.")
else:
    print("Failed to connect to the database.")

# Middleware object between SQLite DB and SQL Commands
cursor = conn.cursor()
print(cursor)

def log_event(event_type: str, distance: Optional[float] = None):
    """
    Logs an event with the given type and data.
    
    Args:
        event_type (str): The type of the event.
        distance: distance of lift (if lift event)
    """
    
    

    if event_type == "lift":
        if not distance:
            raise ValueError("Distance must be provided for lift events.")
            # Insert into database    
        pass
    elif event_type == "pellet_taken":
        # Logic for logging pellet taken event
        # Insert data into database via rsync
        pass
    else:
        raise ValueError("Invalid event type. Must be 'lift' or 'pellet_taken'.")
    