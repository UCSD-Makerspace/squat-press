import pigpio
from time import sleep

# Default Pin Definitions
DIR_PIN = 23
STEP_PIN = 24
MS1_PIN = 22
MS2_PIN = 27
EN_PIN = 17
CPR = 200

class MicrosteppingMode(tuple):
    FULL = (0, 0)
    HALF = (1, 0)
    QUARTER = (0, 1)
    EIGHTH = (1, 1)
    SIXTEENTH = (1, 1)

class StepperMotor:
    def __init__(
        self,
        ms_mode: MicrosteppingMode = MicrosteppingMode.EIGHTH,
        dir_pin: int = DIR_PIN,
        step_pin: int = STEP_PIN,
        ms1_pin: int = MS1_PIN,
        ms2_pin: int = MS2_PIN,
        en_pin: int = EN_PIN,
    ):
        self.pi = pigpio.pi()
        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.ms1_pin = ms1_pin
        self.ms2_pin = ms2_pin
        self.en_pin = en_pin
        self.ms_mode = ms_mode

        # Set GPIO pins as outputs
        for pin in [self.dir_pin, self.step_pin, self.ms1_pin, self.ms2_pin, self.en_pin]:
            if pin != 0: # disabled pins should not be set as input
                self.pi.set_mode(pin, pigpio.INPUT)

    def set_direction(self, direction):
        self.pi.write(self.dir_pin, direction)

    def set_microstepping(self, ms1, ms2):
        self.pi.write(self.ms1_pin, ms1)
        self.pi.write(self.ms2_pin, ms2)

    def set_microstepping_mode(self, mode: MicrosteppingMode):
        ms1, ms2 = mode
        self.set_microstepping(ms1, ms2)

    def step(self, steps: int, delay:float =0.001):
        for _ in range(steps):
            self.pi.write(self.step_pin, 1)
            sleep(delay)
            self.pi.write(self.step_pin, 0)
            sleep(delay)
    
    def rotateDegrees(self, degrees: int, delay:float =0.001):
        """Rotate the motor a certain number of degrees.
        Args:
            degrees (int): The number of degrees to rotate. Positive for clockwise, negative for counter-clockwise.
            delay (float): Delay between steps in seconds.
        """
        if degrees < 0:
            self.set_direction(1) # CW
        else:
            self.set_direction(0) # CCW
        self.step(degrees * CPR * self.ms_mode / 360, delay)

    def __del__(self):
        self.cleanup()
    
    def cleanup(self):
        self.pi.stop()
