# pi/socket_listener.py

import socket
import json
import sqlite3
from contextlib import closing

DB_PATH = 'database/mice_squat.db'  # Adjust if needed
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 5001

def get_unsynced_events():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, device, event_type, distance_lifted FROM events WHERE synced = 0")
        rows = cursor.fetchall()
        events = []
        for row in rows:
            event = {
                "timestamp": row[0],
                "device": row[1],
                "event_type": row[2]
            }
            if row[3] is not None:
                event["distance_lifted"] = row[3]
            events.append(event)
        return events

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Socket listener running on {HOST}:{PORT}")

        while True:
            conn, addr = s.accept()
            with conn:
                try:
                    data = conn.recv(1024)
                    request = json.loads(data.decode('utf-8'))

                    if request.get("request") == "get_unsynced":
                        events = get_unsynced_events()
                        conn.sendall(json.dumps(events).encode('utf-8'))
                    else:
                        conn.sendall(b'{"error": "invalid request"}')
                except Exception as e:
                    print(f"Error handling connection from {addr}: {e}")
                    conn.sendall(b'{"error": "internal error"}')

if __name__ == "__main__":
    run_server()
