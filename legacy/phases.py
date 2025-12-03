from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import time
import threading

MIN_MM, MAX_MM = 7.0, 23.0

@dataclass
class PhaseConfig:
    name: str
    duration: Optional[float] = None
    max_pellets: Optional[int] = None

class Phase(ABC):
    def __init__(self, config: PhaseConfig):
        self.config = config
        self.start_time = None
        self.pellets_dispensed = 0
        self.pellet_queue = 0
        self.pellets_attempted = 0
        self.pending_pellets = 0
        self._lock = threading.Lock()

    @abstractmethod
    def should_dispense(self, mm_value: float, **kwargs) -> bool:
        """Determine if a pellet should be dispensed based on phase logic"""
        pass
    
    @abstractmethod
    def is_complete(self) -> bool:
        """Check if phase is completed"""
        pass

    def start_phase(self):
        with self._lock:
            self.start_time = time.time()
            self.pellets_dispensed = 0
            self.pellet_queue = 0
            self.pellets_attempted = 0
            self.pending_pellets = 0
    
    def add_to_queue(self):
        with self._lock:
            self.pellet_queue += 1

    def pellet_attempt_started(self):
        with self._lock:
            self.pellets_attempted += 1
            self.pending_pellets += 1
            if self.pellet_queue > 0:
                self.pellet_queue -= 1

    def pellet_confirmed_dispensed(self):
        with self._lock:
            self.pellets_dispensed += 1
            if self.pellet_queue > 0:
                self.pellet_queue -= 1
            self._on_pellet_dispensed()

    def pellet_attempt_failed(self):
        with self._lock:
            if self.pending_pellets > 0:
                self.pending_pellets -= 1

    def _on_pellet_dispensed(self):
        pass

    def should_dispense(self, mm_value: float, **kwargs) -> bool:
        pass

    def is_complete(self) -> bool:
        pass

    def _check_common_completion(self):
        """Check common completion criteria (druation/max_pellets)"""
        if self.config.max_pellets and self.pellets_dispensed >= self.config.max_pellets:
            return True
        if self.config.duration and self.start_time:
            return time.time() - self.start_time >= self.config.duration
        return False

class Warmup(Phase):
    def __init__(self, req_lifts: int = 3, lift_increment: int = 1, **kwargs):
        config = PhaseConfig(name="Warmup", **kwargs)
        super().__init__(config)
        self.req_lifts = req_lifts
        self.lift_increment = lift_increment
        self.current_threshold = req_lifts
        self.consecutive_lifts = 0

    def should_dispense(self, mm_value: float, **kwargs) -> bool:
        if mm_value is None:
            return False
        if not (MIN_MM <= mm_value <= MAX_MM):
            return False
        
        self.consecutive_lifts += 1
        if self.consecutive_lifts >= self.current_threshold:
            self.consecutive_lifts = 0
            return True
        return False

    def _on_pellet_dispensed(self):
        """Increment threshold when pellet is confirmed dispensed"""
        self.current_threshold += self.lift_increment

    def is_complete(self) -> bool:
        return self._check_common_completion()
    
class Lift(Phase):
    def __init__(self, 
                 req_lifts: int = 10, 
                 lift_increment: int = 5,
                 threshold_range: tuple[float, float] = (MIN_MM, MAX_MM),
                 duration: float = 60.0, 
                 max_pellets: int = 20):
        
        config = PhaseConfig(
            name="Lift",
            duration=duration,
            max_pellets=max_pellets
        )

        super().__init__(config)

        self.req_lifts = req_lifts
        self.lift_increment = lift_increment
        self.current_threshold = req_lifts
        self.threshold_range = threshold_range
        self.consecutive_lifts = 0

    def should_dispense(self, mm_value, **kwargs):
        if mm_value is None:
            return False
        if not (self.threshold_range[0] <= mm_value <= self.threshold_range[1]):
            return False

        self.consecutive_lifts += 1

        if self.consecutive_lifts >= self.current_threshold:
            self.consecutive_lifts = 0
            return True
        
        return False
    
    def pellet_dispensed(self):
        super().pellet_dispensed()
        self.current_threshold += self.lift_increment

    def is_complete(self):
        return self._check_common_completion()
    
class Cooldown(Phase):
    def __init__(self,
                 pellet_interval: float = 60.0,
                 duration: Optional[float] = 121.0,
                 max_pellets: Optional[int] = None):
        
        config = PhaseConfig(
            name="Cooldown",
            duration=duration,
            max_pellets=max_pellets
        )
        super().__init__(config)
        self.pellet_interval = pellet_interval
        self.last_pellet_time = 0

    def should_dispense(self, mm_value: float, **kwargs) -> bool:
        if mm_value is None:
            return False
        current_time = time.time()
        if current_time - self.last_pellet_time >= self.pellet_interval:
            self.last_pellet_time = current_time
            return True
        return False
    
    def is_complete(self):
        return self._check_common_completion()
    
class ProgressiveOverload(Phase):
    def __init__(self,
                 initial_req_lifts: int = 3,
                 max_req_lifts: int = 10,
                 increment_every_n_pellets: int = 3,
                 threshold_range: tuple[float, float] = (MIN_MM, MAX_MM),
                 duration: float = None,
                 max_pellets: Optional[int] = None):
        
        config=PhaseConfig(
            name="ProgressiveOverload",
            duration=duration,
            max_pellets=max_pellets
        )
        super().__init__(config)

        self.initial_req_lifts = initial_req_lifts
        self.max_req_lifts = max_req_lifts
        self.increment_every_n_pellets = increment_every_n_pellets
        self.threshold_range = threshold_range
        self.current_req_lifts = initial_req_lifts
        self.consecutive_lifts = 0

    def should_dispense(self, mm_value, **kwargs) -> bool:
        if not (self.threshold_range[0] <= mm_value <= self.threshold_range[1]):
            return False
        
        self.consecutive_lifts += 1

        if self.consecutive_lifts >= self.current_req_lifts:
            self.consecutive_lifts = 0
            return True
    
        return False
    
    def pellet_dispensed(self):
        super().pellet_dispensed()

        if self.pellets_dispensed % self.increment_every_n_pellets == 0:
            self.current_req_lifts = min(
                self.current_req_lifts + 1,
                self.max_req_lifts
            )

    def is_complete(self) -> bool:
        return self._check_common_completion()