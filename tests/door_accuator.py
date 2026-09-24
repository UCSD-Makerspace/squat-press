import time
import pigpio

# GPIO pin setup
EN = 15   # Enable
A1 = 6    # Direction 1
A2 = 5    # Direction 2

# Connect to pigpio daemon
pi = pigpio.pi()
if not pi.connected:
    print("Failed to connect to pigpio daemon")
    exit()

# Set pins as outputs
pi.set_mode(EN, pigpio.OUTPUT)
pi.set_mode(A1, pigpio.OUTPUT)
pi.set_mode(A2, pigpio.OUTPUT)

pi.set_PWM_frequency(EN, 200)

try:
    while True:
        # Extend actuator
        print("Extending...")
        pi.write(A1, 1)
        pi.write(A2, 0)
        # pi.write(EN, 1)           # Enable motor
        pi.set_PWM_dutycycle(EN, 200)
        time.sleep(2)             # Run for 5 seconds

        # Stop actuator
        print("Stopping...")
        # pi.write(EN, 0)
        pi.set_PWM_dutycycle(EN, 0)
        time.sleep(2)

        # Retract actuator
        print("Retracting...")
        pi.write(A1, 0)
        pi.write(A2, 1)
        # pi.write(EN, 1)
        pi.set_PWM_dutycycle(EN, 200)
        time.sleep(2)

        # Stop actuator
        print("Stopping...")
        # pi.write(EN, 0)
        pi.set_PWM_dutycycle(EN, 0)
        time.sleep(2)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    # Ensure all pins are low
    pi.write(EN, 0)
    pi.write(A1, 0)
    pi.write(A2, 0)
    pi.stop()
