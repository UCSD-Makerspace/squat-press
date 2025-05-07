import pigpio
from time import sleep
from enum import Enum
from typing import Tuple
from threading import Thread
import logging

# Default Pin Definitions
DIR_PIN = 23
STEP_PIN = 24
MS1_PIN = 22
MS2_PIN = 27
EN_PIN = 17
SPR = 200 # 200 spr = 1.8 degrees per step


class MicrosteppingMode(Enum):
    FULL = 1
    HALF = 2
    QUARTER = 4
    EIGHTH = 8
    SIXTEENTH = 16

    @property
    def pin_values(self) -> Tuple[int, int]:
        _pin_values = {
            MicrosteppingMode.FULL: (0, 0),
            MicrosteppingMode.HALF: (1, 0),
            MicrosteppingMode.QUARTER: (0, 1),
            MicrosteppingMode.EIGHTH: (1, 1),
            MicrosteppingMode.SIXTEENTH: (1, 1),
        }
        return _pin_values[self]

class Direction(Enum):
    COUNTERCLOCKWISE = 0
    CLOCKWISE = 1

    @property
    def sign(self) -> int:
        return 1 if self == Direction.COUNTERCLOCKWISE else -1

class StepperMotor:
    def __init__(
        self,
        ms_mode: MicrosteppingMode = MicrosteppingMode.EIGHTH,
        dir_pin: int = DIR_PIN,
        step_pin: int = STEP_PIN,
        ms1_pin: int = MS1_PIN,
        ms2_pin: int = MS2_PIN,
        en_pin: int = EN_PIN,
        pi: pigpio.pi = None,
        spr: int = SPR,
        start_position: float = 0
    ):
        self.pi = pigpio.pi() if pi is None else pi
        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.ms1_pin = ms1_pin
        self.ms2_pin = ms2_pin
        self.en_pin = en_pin
        self.ms_mode = ms_mode
        self._enabled = False
        self.spr = spr
        self._position = start_position
        self._direction = Direction.CLOCKWISE

        # Set GPIO pins as outputs
        for pin in [self.dir_pin, self.step_pin, self.ms1_pin, self.ms2_pin, self.en_pin]:
            if pin != 0: # disabled pins should not be set as input
                self.pi.set_mode(pin, pigpio.INPUT)

    def set_direction(self, direction: Direction):
        """Set the direction of the motor."""
        self._direction = direction
        self.pi.write(self.dir_pin, direction.value)

    @property
    def position(self) -> float:
        """Get the current position of the motor, in counter-clockwise revolutions."""
        return self._position

    @property
    def direction(self) -> Direction:
        """Get the current direction of the motor."""
        return self._direction

    @property
    def enabled(self) -> bool:
        """Check if the motor is enabled."""
        return self._enabled

    def stop(self):
        logging.info("Stopping motor.")
        self._disable()

    def _enable(self):
        self._enabled = True
        if self.en_pin != 0:
            self.pi.write(self.en_pin, 0)

    def _disable(self):
        self._enabled = False
        if self.en_pin != 0:
            self.pi.write(self.en_pin, 1)

    def set_microstepping(self, ms1: int, ms2: int):
        self.pi.write(self.ms1_pin, ms1)
        self.pi.write(self.ms2_pin, ms2)

    def set_microstepping_mode(self, mode: MicrosteppingMode):
        ms1, ms2 = mode.pin_values
        self.set_microstepping(ms1, ms2)

    def step(self, steps: int, delay:float =0.001):
        if self._enabled:
            logging.warning("Motor is already enabled. Skipping step.")
            return
        self._enable()

        # Step the motor the specified number of times
        for _ in range(steps):
            if not self._enabled:
                logging.log("Motor has been disabled. Stopping stepping.")
                break
            self.pi.write(self.step_pin, 1)
            sleep(delay)
            self.pi.write(self.step_pin, 0)
            sleep(delay)

            # Keep track of the position
            self._position += (1 / self.ms_mode.value) * (self._direction.sign)

        self._disable()

    def step_threaded(self, steps: int, delay:float =0.001) -> Tuple[Thread, Thread]:
        """Step the motor a certain number of steps in a separate thread.
        Args:
            steps (int): The number of steps to take.
            delay (float): Delay between steps in seconds.
        """
        if self._enabled:
            logging.warning("Motor is already enabled. Skipping step.")
            return

        thread = Thread(target=self.step, args=(steps, delay))
        thread.start()

        # Only necessary if we switch to multiprocessing later, but good to have
        def wait_for_end():
            """Make sure that the driver is disabled even if the thread is interrupted."""
            thread.join()
            self._disable()

        waiting_thread = Thread(target=wait_for_end)
        waiting_thread.start()
        return (thread, waiting_thread)

    def rotate_degrees(self, degrees: int, delay:float =0.001):
        """Rotate the motor a certain number of degrees.
        Args:
            degrees (int): The number of degrees to rotate. Positive for clockwise, negative for counter-clockwise.
            delay (float): Delay between steps in seconds.
        """
        if degrees == 0: 
            return
        self.set_direction(Direction.CLOCKWISE if degrees < 0 else Direction.COUNTERCLOCKWISE)
        self.step(int(abs(degrees) * self.spr * self.ms_mode.value / 360), delay)

    def rotate_degrees_threaded(self, degrees: int, delay:float =0.001) -> Tuple[Thread, Thread]:
        """Rotate the motor a certain number of degrees in a separate thread.
        Args:
            degrees (int): The number of degrees to rotate. Positive for clockwise, negative for counter-clockwise.
            delay (float): Delay between steps in seconds.
        """
        if degrees == 0: 
            return
        self.set_direction(Direction.CLOCKWISE if degrees < 0 else Direction.COUNTERCLOCKWISE)
        return self.step_threaded(int(abs(degrees) * self.spr * self.ms_mode.value / 360), delay)

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        logging.info("Shutting down motor.")
        self._disable()
        try:
            self.pi.stop()
        except Exception as e:
            logging.error(f"Error stopping pigpio: {e}")
        else:
            logging.info("Pigpio stopped successfully.")
