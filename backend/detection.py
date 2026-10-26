"""
AI-Based Smart Traffic Management System
Module: Vehicle Detection Pipeline (Computer Vision)
"""

import os
import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("detection")

# Base directory paths (project-relative, independent of current working directory)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DEFAULT_YOLO_PATH = os.path.join(MODELS_DIR, "yolov8n.pt")

# Standard zero-based COCO vehicle classes used by YOLOv8
COCO_VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

EMERGENCY_CLASSES = {"ambulance", "fire truck", "police"}

COLOR_PALETTE = {
    "car": (46, 204, 113),         # Green
    "bus": (241, 196, 15),         # Yellow
    "truck": (52, 152, 219),       # Blue
    "motorcycle": (155, 89, 182),   # Purple
    "bicycle": (26, 188, 156),     # Turquoise
    "emergency": (231, 76, 60),    # Red
    "default": (189, 195, 199)     # Gray
}


class VehicleDetector:
    """
    Multi-backend Vehicle Detector.
    Primary: Ultralytics YOLOv8n deep learning object detector.
    Fallback: Classical CV contour and road-surface contrast detector.
    """

    def __init__(
        self,
        backend: str = "contour",
        confidence_threshold: float = 0.35,
        model_path: Optional[str] = None
    ):
        self.backend_type = backend
        self.conf_threshold = confidence_threshold
        self.model_path = model_path or DEFAULT_YOLO_PATH
        self.model = None
        self.device = "cpu"
        self._init_backend()

    def _init_backend(self):
        """Initializes YOLOv8n as primary detector with automatic contour fallback."""
        # 1. Attempt YOLOv8 (Ultralytics)
        if self.backend_type in ("auto", "yolo"):
            try:
                from ultralytics import YOLO
                target_weights = self.model_path
                # Check models/ directory first, then root as backup
                if not os.path.exists(target_weights):
                    root_weights = os.path.join(BASE_DIR, "yolov8n.pt")
                    if os.path.exists(root_weights):
                        target_weights = root_weights

                if os.path.exists(target_weights):
                    self.model = YOLO(target_weights)
                    self.backend_type = "yolo"
                    logger.info("Active Detection Engine: YOLOv8n Deep Learning (loaded from %s)", target_weights)
                    return
                elif self.backend_type == "yolo":
                    logger.warning("YOLO weights not found at %s. Falling back to contour detection.", target_weights)
            except Exception as e:
                logger.warning("YOLOv8 initialization skipped (%s). Activating classical CV fallback.", e)

        # 2. Offline classical computer vision (Contour + Road Surface Contrast)
        self.backend_type = "contour"
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=40, detectShadows=True)
        logger.info("Active Detection Engine: Classical CV Contour/Contrast (Fallback)")

    def detect(self, frame: np.ndarray, is_synthetic: bool = False) -> List[Dict]:
        """
        Detects vehicles in the provided video frame.
        
        Args:
            frame: BGR image array.
            is_synthetic: When True (synthetic simulator frames), uses the fast OpenCV
                          contour/contrast detector (1ms) tailored for 2D road geometry.
                          When False (real video / webcam), uses YOLOv8n deep learning
                          with automatic contour fallback.

        Returns:
            List of detected objects, each formatted as:
            {
                'bbox': [x1, y1, x2, y2],
                'class_name': str,
                'confidence': float,
                'center': (cx, cy),
                'is_emergency': bool
            }
        """
        if frame is None or frame.size == 0 or np.mean(frame) < 5:
            return []

        # Fast path for synthetic 2D geometric simulation frames
        if is_synthetic:
            return self._detect_contours(frame)

        # Real-world video/webcam frame detection using YOLOv8n (with contour fallback)
        if self.backend_type == "yolo":
            try:
                return self._detect_yolo(frame)
            except Exception as e:
                logger.warning("YOLO inference failed (%s). Falling back to contour detector.", e)
                return self._detect_contours(frame)
        elif self.backend_type == "torchvision":
            return self._detect_torchvision(frame)
        else:
            return self._detect_contours(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[Dict]:
        """Runs YOLOv8 inference and maps detections to standardized format."""
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        detections = []
        h, w = frame.shape[:2]

        for box in results.boxes:
            cls_id = int(box.cls[0].item())
            if cls_id not in COCO_VEHICLE_CLASSES:
                continue

            cls_name = COCO_VEHICLE_CLASSES[cls_id]
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            # Clamp coordinates to frame boundaries
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            is_emergency = self._check_emergency_visual_cues(frame, x1, y1, x2, y2)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            detections.append({
                "bbox": [x1, y1, x2, y2],
                "class_name": "emergency" if is_emergency else cls_name,
                "confidence": round(conf, 2),
                "center": (cx, cy),
                "is_emergency": is_emergency
            })
        return detections

    def _detect_torchvision(self, frame: np.ndarray) -> List[Dict]:
        import torch
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_tensor = self.torchvision_transforms(torch.from_numpy(rgb_frame).permute(2, 0, 1)).unsqueeze(0).to(self.device)

        with torch.no_grad():
            predictions = self.model(input_tensor)[0]

        detections = []
        h, w = frame.shape[:2]
        boxes = predictions["boxes"].cpu().numpy()
        labels = predictions["labels"].cpu().numpy()
        scores = predictions["scores"].cpu().numpy()

        for box, label, score in zip(boxes, labels, scores):
            if score < self.conf_threshold:
                continue
            if label in VEHICLE_CLASSES:
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                cls_name = VEHICLE_CLASSES[label]
                is_emergency = self._check_emergency_visual_cues(frame, x1, y1, x2, y2)

                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "class_name": "emergency" if is_emergency else cls_name,
                    "confidence": round(float(score), 2),
                    "center": (cx, cy),
                    "is_emergency": is_emergency
                })
        return detections

    def _detect_contours(self, frame: np.ndarray) -> List[Dict]:
        """Contour and contrast detection for vehicles in roadway frames."""
        if frame is None or frame.size == 0 or np.mean(frame) < 5:
            return []

        h, w = frame.shape[:2]
        asphalt = np.array([38, 42, 46], dtype=np.uint8)
        diff = cv2.absdiff(frame, asphalt)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

        # Focus strictly on the active roadway between curbs (curbs at 180 and 460)
        road_mask = np.zeros((h, w), dtype=np.uint8)
        road_mask[10:h - 10, 192:448] = 255
        road_diff = cv2.bitwise_and(gray_diff, road_mask)

        _, thresh = cv2.threshold(road_diff, 28, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 400:
                x, y, bw, bh = cv2.boundingRect(cnt)
                x2, y2 = x + bw, y + bh
                cx = x + bw // 2
                cy = y + bh // 2

                # Filter out thin lane dividers, curb edges, horizontal text, or giant road contours
                if bw < 14 or bh < 24 or bw > 65 or bh > 140:
                    continue
                # Vehicles driving vertically have height > width
                if (float(bw) / max(bh, 1)) > 0.85:
                    continue
                # Exclude top intersection text zone
                if cy < 80 and bw > 40:
                    continue

                # Classify based on bounding box geometry
                if area > 3500 or bh > 95:
                    cls_name = "truck" if bh > 105 else "bus"
                elif area > 1400 or bh > 50:
                    cls_name = "car"
                else:
                    cls_name = "motorcycle"

                is_emergency = self._check_emergency_visual_cues(frame, x, y, x2, y2)

                detections.append({
                    "bbox": [x, y, x2, y2],
                    "class_name": "emergency" if is_emergency else cls_name,
                    "confidence": 0.85,
                    "center": (cx, cy),
                    "is_emergency": is_emergency
                })
        return detections

    def _check_emergency_visual_cues(self, frame: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> bool:
        """
        Visual heuristic for detecting emergency vehicles (ambulances/fire trucks)
        via co-occurring red and blue strobes and white vehicle body.
        Prevents false positives on standard red passenger cars.
        """
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 10 or y2 - y1 < 10:
            return False

        roi = frame[y1:y2, x1:x2]

        # 1. Check for blue strobe pixels (B is high, R and G are low)
        blue_pixels = int(np.sum((roi[:, :, 0] > 180) & (roi[:, :, 1] < 110) & (roi[:, :, 2] < 110)))

        # 2. Check for red strobe/cross pixels (R is high, B and G are low)
        red_pixels = int(np.sum((roi[:, :, 2] > 180) & (roi[:, :, 1] < 110) & (roi[:, :, 0] < 110)))

        # 3. Check for white ambulance body pixels
        white_pixels = int(np.sum((roi[:, :, 0] > 200) & (roi[:, :, 1] > 200) & (roi[:, :, 2] > 200)))

        # True ambulance has co-occurring red and blue strobes with white body
        if blue_pixels >= 15 and red_pixels >= 15 and white_pixels >= 100:
            return True

        # Secondary HSV check for video footage where strobes alternate
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower_red1 = np.array([0, 100, 80])
        upper_red1 = np.array([12, 255, 255])
        lower_red2 = np.array([168, 100, 80])
        upper_red2 = np.array([180, 255, 255])
        red_mask = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)

        lower_blue = np.array([100, 100, 80])
        upper_blue = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        # Both red and blue indicators must be present simultaneously
        has_dual_strobes = (np.sum(red_mask > 0) > 25) and (np.sum(blue_mask > 0) > 25)
        return bool(has_dual_strobes)

    def draw_annotations(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        lane_polygons: Optional[Dict[str, np.ndarray]] = None,
        header_text: Optional[str] = None
    ) -> np.ndarray:
        """
        Overlays bounding boxes, labels, centroids, and lane zones onto frame.
        """
        output = frame.copy()

        # 1. Draw Lane Regions of Interest (ROI) if provided
        if lane_polygons:
            overlay = output.copy()
            for lane_id, poly in lane_polygons.items():
                pts = np.array(poly, np.int32).reshape((-1, 1, 2))
                cv2.polylines(overlay, [pts], isClosed=True, color=(255, 255, 0), thickness=2)
                cv2.fillPoly(overlay, [pts], color=(30, 144, 255))
            cv2.addWeighted(overlay, 0.2, output, 0.8, 0, output)

        # 2. Draw Detected Vehicles
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cls_name = det["class_name"]
            conf = det["confidence"]
            is_emergency = det["is_emergency"]

            color = COLOR_PALETTE["emergency"] if is_emergency else COLOR_PALETTE.get(cls_name, COLOR_PALETTE["default"])

            # Bounding box
            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

            # Centroid
            cx, cy = det["center"]
            cv2.circle(output, (cx, cy), 4, color, -1)

            # Label banner
            label = f"EMERGENCY" if is_emergency else f"{cls_name.capitalize()} {int(conf*100)}%"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            # Label background badge
            cv2.rectangle(output, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, max(0, y1)), color, -1)
            cv2.putText(output, label, (x1 + 3, max(0, y1 - 4)), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # 3. Header HUD
        if header_text:
            cv2.rectangle(output, (0, 0), (output.shape[1], 36), (20, 24, 33), -1)
            cv2.putText(output, header_text, (14, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2, cv2.LINE_AA)

        return output
