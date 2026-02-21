import cv2
from datetime import datetime
import sys

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

cap.set(cv2.CAP_PROP_FPS, 30)

actual_fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"Camera actual settings: {width}x{height} @ {actual_fps} FPS")

fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f'squat_recording_{timestamp}.mp4'

out = cv2.VideoWriter(filename, fourcc, actual_fps, (width, height))

print("REC started... Press Ctrl+C to stop.")

try:
    while True:
        ret, frame = cap.read()
        if not ret: break
        out.write(frame)
except KeyboardInterrupt:
    print("\nSaving...")
finally:
    cap.release()
    out.release()
    print(f"Done! Saved as {filename}")
    sys.exit()