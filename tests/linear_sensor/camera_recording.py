import cv2
import sys

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
timestamp = cv2.getTickCount()
out = cv2.VideoWriter('squat_recording{time}.mp4'.format(time=timestamp), fourcc, 20.0, (1280, 720))

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
    print("Done! Video saved as squat_recording{time}.mp4".format(time=timestamp))
    sys.exit()