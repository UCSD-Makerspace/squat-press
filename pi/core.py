import lx3302a.SENTReader.SENTReader as SENTReader
from lx3302a.SENTReader.interpolate import interpolate
import time
import pigpio

#### Consts ####
SENT_GPIO = 18

# Core loop for hardware communication #
def main():
    pi = pigpio.pi()
    p = SENTReader.SENTReader(pi, SENT_GPIO)

    # Needed functions
    motor.rotate()
    
    pellet.dispense()
    

    beambreak.record_event()
    