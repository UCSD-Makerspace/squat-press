from PhotoInterruptor import PhotoInterruptor
from pi.database import log_event
import time

RUN_TIME = 6000000000.0
PELLET_DISPENSED, PELLET_TAKEN = "pellet_dispensed", "pellet_taken"

def main():
    last_state = LTC.get_detected()
    start = time.time()

    while (time.time() - start) < RUN_TIME:
        time.sleep(0.1)
        LTC.update()
        cur_state = LTC.get_detected()

        if last_state is False and cur_state is True:
            print(f"Pellet dispensed: {LTC.get_detected()}, Data: {LTC.get_data_percent():0.5f}")
            logger(PELLET_DISPENSED, LTC)
        if last_state is True and cur_state is False:
            logger(PELLET_TAKEN, LTC)

        last_state = cur_state

def logger(event_type, LTC):
    print(f"Logging event: {event_type}, Data: {LTC.get_data_percent():0.5f}")
    log_event(
        event_type=event_type,
        event_data={
            "detected": LTC.get_detected(),
            "data_percent": LTC.get_data_percent()
        }
    )

if __name__ == "__main__":
    LTC = PhotoInterruptor()
    main()


