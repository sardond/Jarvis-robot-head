import cv2
import numpy as np
from picamera2 import Picamera2
import serial
import time

# ================= SERIAL =================
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=0.01)
time.sleep(2)

# ================= DNN MODEL PATHS =================
PROTO = "/home/tom/dnn/deploy.prototxt"
MODEL = "/home/tom/dnn/res10_300x300_ssd_iter_140000.caffemodel"

net = cv2.dnn.readNetFromCaffe(PROTO, MODEL)

# ================= CAMERA =================
picam = Picamera2()
config = picam.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"}
)
picam.configure(config)
picam.start()

# ================= TRACKING STATE =================
smooth_x = 320
smooth_y = 240

alpha = 0.25          # smoothing (lower = smoother)
dead_zone = 6         # ignore tiny jitter
conf_threshold = 0.6  # face confidence
lost_frames = 0
lost_limit = 12       # frames before drifting home

print("DNN Face tracking started")

# ================= MAIN LOOP =================
while True:
    frame = picam.capture_array()
    (h, w) = frame.shape[:2]

    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)),
        1.0,
        (300, 300),
        (104.0, 177.0, 123.0)
    )

    net.setInput(blob)
    detections = net.forward()

    cx = -1
    cy = -1
    best_conf = 0

    # ===== Select strongest face =====
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]

        if confidence > conf_threshold and confidence > best_conf:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            best_conf = confidence

    if cx != -1:
        lost_frames = 0

        dx = cx - smooth_x
        dy = cy - smooth_y

        if abs(dx) > dead_zone:
            smooth_x = smooth_x * (1 - alpha) + cx * alpha
        if abs(dy) > dead_zone:
            smooth_y = smooth_y * (1 - alpha) + cy * alpha

        # Draw debug
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(frame, (int(smooth_x), int(smooth_y)), 5, (255, 0, 0), -1)

    else:
        lost_frames += 1
        if lost_frames > lost_limit:
            smooth_x = smooth_x * 0.97 + 320 * 0.03
            smooth_y = smooth_y * 0.97 + 240 * 0.03

    # ===== SEND TO ARDUINO =====
    # Normalize X to -1.0 ... +1.0
  #  norm_x = (smooth_x - 320) / 320
    ser.write(f"{int(smooth_x)},{int(smooth_y)}\n".encode())

  #  cv2.imshow("DNN Face Tracking", frame)
  #  if cv2.waitKey(1) & 0xFF == ord('q'):
  #     break

picam.stop()
cv2.destroyAllWindows()
ser.close()
