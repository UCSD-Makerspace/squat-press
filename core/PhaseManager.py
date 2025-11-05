import time
import logging
from typing import List, Optional
from phases import Phase

class PhaseManager():
    def __init__(self, phases: List[Phase] = None):
        self.phases = phases or []
        self.current_phase_index = 0
        self.current_phase = None
        self.trial_start_time = None
        self.is_trial_active = False

    def add_phase(self, phase: Phase) -> None:
        self.phases.append(phase)

    def insert_phase(self, index: int, phase: Phase) -> None:
        self.phases.insert(index, phase)

    def remove_phase(self, index: int) -> Optional[Phase]:
        if 0 <= index < len(self.phases):
            return self.phases.pop(index)
        return None

    def start_trial(self) -> bool:
        if not self.phases:
            logging.warning("No available phases to start")
            return False
        
        self.trial_start_time = time.time()
        self.current_phase_index = 0
        self.is_trial_active = True


        self.current_phase = self.phases[0]
        self.current_phase.start_phase()    

        logging.info(f"Trial phase {self.current_phase.config.name} has began")
        return True

    def get_current_phase(self) -> Optional[Phase]:
        return self.current_phase if self.is_trial_active else None
    
    def advance_to_next_phase(self) -> Optional[Phase]:
        if not self.is_trial_active:
            logging.warning("Cannot advance to next phase! No trial active")
            return None
    
        if self.current_phase_index + 1 >= len(self.phases):
            logging.info("Trial completed, last phase reached. Ending trial.")
            self.end_trial()
            return None
    
        self.current_phase_index += 1
        self.current_phase = self.phases[self.current_phase_index]
        self.current_phase.start_phase()

        logging.info(f"Proceeding to phase: {self.current_phase.config.name}")
        return self.current_phase

    def check_phase_completion(self) -> bool:
        if not self.is_trial_active or not self.current_phase:
            return False
        
        if self.current_phase.is_complete():
            logging.info(f"Phase '{self.current_phase.config.name}' completed")
            old_phase = self.current_phase
            new_phase = self.advance_to_next_phase()

            if hasattr(old_phase, 'pellets_dispensed'):
                logging.info(f"{old_phase} stats - Pellets dispensed: {old_phase.pellets_dispensed}")

            return new_phase is not None
        
        return False
    
    def end_trial(self) -> None:
        if self.is_trial_active:
            trial_duration = time.time() - self.trial_start_time
            logging.info(f"Trial ended after {trial_duration:.2f} seconds")

        self.is_trial_active = False
        self.current_phase = None
        self.current_phase_index = 0

    def get_trial_stats(self) -> dict:
        stats = {
            'is_active': self.is_trial_active,
            'total_phases': len(self.phases),
            'current_phase_index': self.current_phase_index,
            'current_phase_name': self.current_phase.config.name if self.current_phase else None,
            'trial_duration': time.time() - self.trial_start_time if self.trial_start_time else 0,
            'phases_completed': self.current_phase_index,
            'phases_remaining': len(self.phases) - self.current_phase_index -1 if self.is_trial_active else 0
        }

        if self.current_phase:
            stats['current_phase_stats'] = {
                'pellets_dispensed': getattr(self.current_phase, 'pellets_dispensed', 0),
                'pellet_queue': getattr(self.current_phase, 'pellet_queue', 0),
                'phase_duration': time.time() - self.current_phase.start_time if self.current_phase.start_time else 0
            }

        return stats
    
    def force_advance_phase(self) -> Optional[Phase]:
        if not self.is_trial_active:
            logging.warning("Cannot force advance phase - trial not active")
            return None
        
        logging.info(f"Manually advancing from phase: {self.current_phase.config.name}")
        return self.advance_to_next_phase()
    
    def reset_trial(self) -> None:
        if self.is_trial_active:
            logging.info("Resetting trial to first phase")
            self.current_phase_index = 0
            self.current_phase = self.phases[0] if self.phases else None
            if self.current_phase:
                self.current_phase.start_phase()

    def get_phase_list(self) -> List[str]:
        if self.phases:
            return [phase.config.name for phase in self.phases]
        else: return None

    def is_trial_complete(self) -> bool:
        return not self.is_trial_active
    
    def __repr__(self) -> str:
        status = "Active" if self.is_trial_active else "Inactive"
        current = self.current_phase.config.name if self.current_phase else "None"
        return f"PhaseManager(status={status}, current_phase={current}, phases={len(self.phases)})"
    
    def log_trial_progress(self, pending_count):
        stats = self.get_trial_stats()
        if stats['current_phase_stats']:
            cps = stats['current_phase_stats']
            logging.info(f"Trial progress: Phase {stats['current_phase_name']}, "
                        f"Pellets: {cps['pellets_dispensed']}, "
                        f"Queue: {cps['pellet_queue']}, "
                        f"Pending confirmations: {pending_count}")
        