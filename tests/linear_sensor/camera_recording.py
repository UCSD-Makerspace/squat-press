import cv2
import sys

# 1. Initialize Camera
cap = cv2.VideoCapture(0)

# 2. Set Resolution (1280x720 is a good 'High Def' balance for Pi)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# 3. Define the MP4 Codec and Output File
fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
out = cv2.VideoWriter('squat_recording.mp4', fourcc, 20.0, (1280, 720))

print("REC started... Press Ctrl+C to stop and save.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Camera disconnected.")
            break
            
        # Save the frame to the file
        out.write(frame)
        
except KeyboardInterrupt:
    # This happens when you press Ctrl+C
    print("\nStopping recording and saving file...")

finally:
    # 4. Crucial: Release the resources so the file actually writes to disk
    cap.release()
    out.release()
    print("Done! Video saved as squat_recording.mp4")
    sys.exit()