import SENTReader
import time
import pigpio
import sys
from os import path
sys.path.append(path.abspath('../Dispenser/tmc2209.py'))
import tmc2209
import DAC

def main():
    SENT_GPIO = 18
    RUN_TIME = 6000000000.0
    SAMPLE_TIME = 0.1

    pi = pigpio.pi()

    # p = SENTReader.SENTReader(pi, SENT_GPIO)
    dac = DAC.DAC(pi)

    start = time.time()

    most_recent_data = 0
    time_since_last_data = 0
    filtered_data = 0
    alpha = 0.6
    motor = tmc2209.TMC2209()
    motor.set_microstepping_mode(tmc2209.MicrosteppingMode.SIXTYFOURTH)
    dir = 1
    threshold = 0.7
    belowThreshold = False
    while (time.time() - start) < RUN_TIME:
        
        time.sleep(SAMPLE_TIME)
        # For SENT 
        # status, data1, data2, ticktime, crc, errors, syncPulse = p.SENTData()
        # if errors == 0 or errors == 8:
        #     most_recent_data = data1
        #     time_since_last_data = 0
        # else:
        #     time_since_last_data += SAMPLE_TIME
        #     if time_since_last_data > 5.0:
        #         print("No valid data received for 5 seconds, restarting SENTReader")
        #         p.stop()
        #         p = SENTReader.SENTReader(pi, SENT_GPIO)
        #         time.sleep(3.0)
        #         time_since_last_data = 0
        #         continue
        dac.update()
        data = dac.get_data()
        if data == 0:
            print("Out of bounds!")
            continue

        most_recent_data = data

        filtered_data = (filtered_data * alpha) + (most_recent_data * (1-alpha))
        print(f"Filtered Pos, {filtered_data:0.5f}, Current Pos, {most_recent_data}")

        if filtered_data < threshold and not belowThreshold:
            belowThreshold = True
            
            dist = dir*180
            thread, _ = motor.rotate_degrees_threaded(dist, 0)
            print(f"Dispensing Pellet...")
        if filtered_data > threshold and belowThreshold:
            belowThreshold = False

        # print(f"Sent Status= {status}, 12-bit DATA 1= {data1:4.0f}, DATA 2= {data2:4.0f} " +
        #       f", tickTime(uS)= {ticktime:4.0f}, CRC= {crc}, Errors= {errors:4b}, PERIOD = {syncPulse}")

    # clear the pi object instance
    pi.stop()

if __name__ == "__main__":
    main()
