import cv2

# OV7670 index should be 0
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Cannot open camera. Check wiring and dtoverlay.")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    cv2.imshow('OV7670 Feed', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()