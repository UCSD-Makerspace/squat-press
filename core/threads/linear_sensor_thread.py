import threading, time
from collections import deque
from typing import Optional
from events import EventType

"""
Thread to monitor linear sensor for lift detection events.
"""
class LinearSensorThread(threading.Thread):
    def __init__(self, linear_sensor, event_queue, mm_threshold=10, recent_lifts: Optional[deque]=None):
        super().__init__(daemon=True)
        self.linear_sensor = linear_sensor
        self.linear_sensor.connect()
        self.queue = event_queue
        self.recent_lifts = recent_lifts
        self.threshold = mm_threshold
        self.last_mm_value = None
        self.in_lift = False

    def run(self):
        while True:
            mm_value = self.linear_sensor.get_position()

            # update recent lifts deque
            if self.recent_lifts is not None:
                if len(self.recent_lifts) > 10:
                    self.recent_lifts.popleft()
                self.recent_lifts.append(mm_value)

            current_time = time.time()

            # lift validation logic
            if mm_value is not None:
                self.last_mm_value = mm_value

                if self.validate_lift(mm_value):
                    self.queue.put((EventType.LIFT_DETECTED, mm_value, current_time))

                    while True:
                        if not self.validate_lift(mm_value):
                            break

                        mm_value = self.linear_sensor.read_mm_value()

                        if self.recent_lifts is not None:
                            if len(self.recent_lifts) > 10:
                                self.recent_lifts.popleft()
                            self.recent_lifts.append(mm_value)
                        
                        time.sleep(0.01)
                        
                    self.queue.put((EventType.LIFT_COMPLETED, mm_value, current_time))
                    
    def read_mm_value(self):
        return self.linear_sensor.get_position()
    
    def calculate_avg_slope(self) -> float:
        if self.recent_lifts is None or len(self.recent_lifts) < 2:
            return 0
        
        slopes = []
        for i in range(1, len(self.recent_lifts)):
            delta_mm = self.recent_lifts[i] - self.recent_lifts[i-1]
            slopes.append(delta_mm)
        
        average = sum(slopes) / len(slopes) if slopes else 0
        return average
    
    def validate_lift(self, mm_value) -> bool:
        if self.recent_lifts is None or len(self.recent_lifts) < 2:
            return False
        
        avg_slope = self.calculate_avg_slope()

        if avg_slope >= 0.1 and mm_value > self.threshold:
            self.in_lift = True
            return True
        
        # even if the slope drops, stay in lift until below 8mm
        if self.in_lift and mm_value > self.threshold - 2:
            return True
        
        if mm_value < self.threshold - 2 or avg_slope <= 0.1:
            self.in_lift = False
            return False

        return False
