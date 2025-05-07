import stepper
from time import sleep

def main():
    motor = stepper.StepperMotor()
    motor.set_microstepping_mode(stepper.MicrosteppingMode.EIGHTH)
    dir = 1
    while True:
        dir = -dir
        motor.rotateDegrees(dir*90, 0.001)
        sleep(1)