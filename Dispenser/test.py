import tmc2209
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
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    dir = 1
    while True:
        dir = -dir
        dist = dir*180
        thread, _ = motor.rotate_degrees_threaded(dist, 0)
        print(f"Rotating {dist} degrees...")
        thread.join()
        print("Rotation complete.")
        print(f"Current position: {motor.position:.2f} revolutions")
        sleep(1)

if __name__ == "__main__":
    main()
