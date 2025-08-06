import sqlite3
from typing import Optional
from datetime import datetime
import json
import os

###############################################################
# Main file for event handling. Inserts events into SQLite DB #
###############################################################

# =========== Configuration ===========
DEVICE_NAME = 'mice_c1'
DB_PATH = os.path.join(os.path.dirname(__file__), 'mice_squat.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

# Connect to the SQLite database
conn = sqlite3.connect(DB_PATH)
if conn:
    print('Connected to the database successfully.')
else:
    print("Failed to connect to the database.")

# Middleware object between SQLite DB and SQL Commands
cursor = conn.cursor()
print(cursor)

# If no table exists, create one with outlined schema.
cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        device TEXT NOT NULL,
        event_type TEXT NOT NULL,
        distance_lifted REAL,
        synced INTEGER DEFAULT 0,
        details_json TEXT     
    )
''')    
conn.commit()

# Main function for event logging.
def log_event(event_type: str, event_data: Optional[float] = None):
    """
    Logs an event with the given type and data.
    
    Args:
        event_type (str): The type of the event.
        distance: (float, optional): Required for 'lift' events
    """
    allowed_types = {'lift', 'pellet_taken', 'pellet_dispensed'}
    if event_type not in allowed_types:
        raise ValueError("Invalid event type. Must be 'lift' or 'pellet_taken'.")
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    distance = None

    if event_type == "lift":
        if not event_data or 'distance_lifted' not in event_data:
            raise ValueError("Missing distance_lifted for lift event")
        distance = event_data['distance_lifted']

    details_json = json.dumps(event_data) if event_data else None

    cursor.execute('''
        INSERT INTO events (timestamp, device, event_type, distance_lifted, synced)
        VALUES (?, ?, ?, ?, 0, ?)
    ''', (timestamp, DEVICE_NAME, event_type, distance, details_json))
    
    conn.commit()
    print(f"Event logged: {event_type} at {timestamp}")