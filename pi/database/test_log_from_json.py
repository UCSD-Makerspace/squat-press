import json
import os
import sys
import log_event

sys.path.append(os.path.dirname(__file__))

mock_file_path = os.path.join(os.path.dirname(__file__), '../mock_data/mock_events.json')

with open(mock_file_path, 'r') as file:
    events = json.load(file)

for event in events:
    event_type = event['event_type']
    distance = event.get('distance_lifted')
    log_event.log_event(event_type = event_type, distance=distance)