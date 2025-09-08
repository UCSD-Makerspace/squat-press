import time
import pigpio

# GPIO pins
EN = 15   # 1,2 EN
IN1 = 6   # 1A
IN2 = 5   # 2A

# Initialize pigpio
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("Could not connect to pigpio daemon. Run 'sudo pigpiod' first.")

# Setup pins
pi.set_mode(EN, pigpio.OUTPUT)
pi.set_mode(IN1, pigpio.OUTPUT)
pi.set_mode(IN2, pigpio.OUTPUT)

# Function to extend actuator
def extend(duration=2.0, speed=255):
    pi.write(IN1, 1)
    pi.write(IN2, 0)
    pi.set_PWM_dutycycle(EN, speed)
    time.sleep(duration)
    stop()

# Function to retract actuator
def retract(duration=2.0, speed=255):
    pi.write(IN1, 0)
    pi.write(IN2, 1)
    pi.set_PWM_dutycycle(EN, speed)
    time.sleep(duration)
    stop()

# Stop actuator
def stop():
    pi.set_PWM_dutycycle(EN, 0)
    pi.write(IN1, 0)
    pi.write(IN2, 0)

# Main loop for testing
try:
    while True:
        cmd = input("Enter command (e=extend, r=retract, s=stop, q=quit): ").lower()
        if cmd == "e":
            extend()
        elif cmd == "r":
            retract()
        elif cmd == "s":
            stop()
        elif cmd == "q":
            stop()
            break
        else:
            print("Invalid command!")

finally:
    stop()
    pi.stop()
