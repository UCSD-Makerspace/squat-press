import cv2
from datetime import datetime
import sys

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
now = datetime.now()
timestamp = now.strftime("%Y%m%d_%H%M%S")

filename = f'squat_recording_{timestamp}.mp4'
out = cv2.VideoWriter(filename, fourcc, 20.0, (1280, 720))

print("REC started... Press Ctrl+C to stop and save.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Camera disconnected.")
            break
            
        out.write(frame)
        
except KeyboardInterrupt:
    print("\nStopping recording and saving file...")

finally:
    cap.release()
    out.release()
    print("Done! Video saved as {}".format(filename))
    sys.exit()