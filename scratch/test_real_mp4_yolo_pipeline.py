import os
import sys
import tempfile
import cv2
import numpy as np

BASE_DIR = r"c:\Users\Nitheesh\OneDrive\Documents\Desktop\Smart-Traffic-Management"
sys.path.insert(0, BASE_DIR)

from backend.detection import VehicleDetector
from backend.traffic_analysis import IntersectionTrafficAnalyzer
from backend.decision_agent import TrafficDecisionAgent

print("=== 1. GENERATING REAL MP4 TRAFFIC VIDEO ===")
temp_mp4 = os.path.join(BASE_DIR, "videos", "traffic_test_yolo.mp4")
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(temp_mp4, fourcc, 25.0, (640, 480))

for f in range(50):
    # Road background
    frame = np.full((480, 640, 3), (45, 45, 45), dtype=np.uint8)
    # Road lanes
    cv2.line(frame, (320, 0), (320, 480), (255, 255, 255), 2)
    # Draw vehicles with realistic colors/shapes
    cv2.rectangle(frame, (180, 100 + f * 4), (260, 240 + f * 4), (20, 30, 200), -1)
    cv2.rectangle(frame, (360, 250 - f * 2), (440, 370 - f * 2), (180, 180, 180), -1)
    out.write(frame)
out.release()
print(f"Created MP4 video: {temp_mp4} ({os.path.getsize(temp_mp4)} bytes)")

print("\n=== 2. TESTING YOLOv8n DETECTION ON REAL MP4 FRAMES ===")
detector = VehicleDetector(backend="auto")
analyzer = IntersectionTrafficAnalyzer()
decision_agent = TrafficDecisionAgent()

cap = cv2.VideoCapture(temp_mp4)
self_opened = cap.isOpened()
print(f"VideoCapture opened successfully: {self_opened}")
assert self_opened, "VideoCapture failed to open"

total_frames_processed = 0
for i in range(15):
    ret, frame = cap.read()
    if not ret or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    assert ret, f"Frame {i} read failed"

    # Run YOLO detection with is_synthetic=False
    detections = detector.detect(frame, is_synthetic=False)
    summary = analyzer.process_lane_detections("north", detections)
    total_frames_processed += 1

print(f"Processed {total_frames_processed} video frames through YOLOv8n detector!")
print(f"Final Analyzer summary for north approach: {summary}")

# Verify decision agent steps
snapshot = analyzer.get_intersection_snapshot()
decision_agent.tick(0.04, snapshot)
print(f"Decision Agent tick succeeded. Current phase: {decision_agent.current_phase}, remaining: {decision_agent.phase_time_remaining:.2f}s")

cap.release()
try:
    os.remove(temp_mp4)
except OSError:
    pass

print("\n=== ALL REAL MP4 TESTS COMPLETED SUCCESSFULLY ===")
