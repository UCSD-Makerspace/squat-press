import stepper
from time import sleep
import pigpio

def test2():
    pi = pigpio.pi()
    pi.set_mode(23, pigpio.OUTPUT)
    pi.set_mode(24, pigpio.OUTPUT)
    print("Starting test")
    for i in range(200*8):
        print("Stepping")
        pi.write(24, 1)
        sleep(0.001)
        pi.write(24, 0)
        sleep(0.001)


def main():
    motor = stepper.StepperMotor()
    motor.set_microstepping_mode(stepper.MicrosteppingMode.EIGHTH)
    dir = 1
    while True:
        dir = -dir
        thread, _ = motor.rotate_degrees_threaded(dir*90, 0.001)
        print(f"Rotating {dir*90} degrees...")
        thread.join()
        print("Rotation complete.")
        print(f"Current position: {motor.position} revolutions")
        sleep(1)

if __name__ == "__main__":
    main()
