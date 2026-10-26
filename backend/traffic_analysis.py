"""
AI-Based Smart Traffic Management System
Module: Traffic Density & Queue Analysis (PCU Metric Engine)
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Optional

# Standard Passenger Car Unit (PCU) equivalents (IRC Standards)
DEFAULT_PCU_WEIGHTS = {
    "car": 1.0,
    "bus": 2.5,
    "truck": 3.0,
    "motorcycle": 0.5,
    "bicycle": 0.2,
    "emergency": 3.5,
    "unknown": 1.0
}

# Maximum nominal capacity per approach lane (in PCUs) for saturation calculation
DEFAULT_MAX_PCU_CAPACITY = 20.0


class LaneTrafficAnalyzer:
    """
    Computes traffic queue length, vehicle class distribution,
    weighted Passenger Car Unit (PCU) density, and emergency vehicle alerts.
    """

    def __init__(
        self,
        lane_id: str,
        name: str = "",
        roi_polygon: Optional[List[List[int]]] = None,
        pcu_weights: Optional[Dict[str, float]] = None,
        max_capacity_pcu: float = DEFAULT_MAX_PCU_CAPACITY
    ):
        self.lane_id = lane_id
        self.name = name or f"Lane {lane_id}"
        self.roi_polygon = np.array(roi_polygon, dtype=np.int32) if roi_polygon else None
        self.pcu_weights = pcu_weights or DEFAULT_PCU_WEIGHTS.copy()
        self.max_capacity_pcu = max_capacity_pcu

        # Metrics state
        self.vehicle_counts = {k: 0 for k in self.pcu_weights.keys()}
        self.total_vehicles = 0
        self.total_pcu = 0.0
        self.density_percentage = 0.0
        self.congestion_level = "Low"
        self.has_emergency = False
        self.emergency_count = 0

    def is_inside_roi(self, point: tuple) -> bool:
        """Determines if a vehicle center coordinate falls within this lane's ROI."""
        if self.roi_polygon is None:
            return True  # If no polygon defined, assume full frame belongs to this lane
        cx, cy = point
        return cv2.pointPolygonTest(self.roi_polygon, (float(cx), float(cy)), False) >= 0

    def analyze(self, detections: List[Dict]) -> Dict[str, Any]:
        """
        Analyzes detected vehicles, aggregates counts, computes PCUs,
        and determines congestion status.
        """
        # Reset counters for the current frame
        counts = {k: 0 for k in self.pcu_weights.keys()}
        total_pcu = 0.0
        emergency_detected = False
        emergency_count = 0

        for det in detections:
            cx, cy = det["center"]
            if not self.is_inside_roi((cx, cy)):
                continue

            cls_name = det.get("class_name", "unknown").lower()
            is_emergency = det.get("is_emergency", False)

            if is_emergency:
                emergency_detected = True
                emergency_count += 1
                cls_name = "emergency"

            weight = self.pcu_weights.get(cls_name, 1.0)
            counts[cls_name] = counts.get(cls_name, 0) + 1
            total_pcu += weight

        total_vehicles = sum(counts.values())
        density_pct = min(100.0, round((total_pcu / max(self.max_capacity_pcu, 1.0)) * 100.0, 1))

        # Congestion classification
        if density_pct >= 85.0:
            congestion_level = "Critical"
        elif density_pct >= 60.0:
            congestion_level = "High"
        elif density_pct >= 30.0:
            congestion_level = "Moderate"
        else:
            congestion_level = "Low"

        # Update instance state
        self.vehicle_counts = counts
        self.total_vehicles = total_vehicles
        self.total_pcu = round(total_pcu, 2)
        self.density_percentage = density_pct
        self.congestion_level = congestion_level
        self.has_emergency = emergency_detected
        self.emergency_count = emergency_count

        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Returns the analytical snapshot for dashboard and decision agent consumption."""
        return {
            "lane_id": self.lane_id,
            "name": self.name,
            "total_vehicles": self.total_vehicles,
            "vehicle_breakdown": self.vehicle_counts,
            "total_pcu": self.total_pcu,
            "density_percentage": self.density_percentage,
            "congestion_level": self.congestion_level,
            "has_emergency": self.has_emergency,
            "emergency_count": self.emergency_count
        }


class IntersectionTrafficAnalyzer:
    """
    Coordinates multi-approach traffic analysis across an entire intersection
    (e.g., North, South, East, West approaches).
    """

    def __init__(self, lane_configs: Optional[List[Dict]] = None):
        self.lanes: Dict[str, LaneTrafficAnalyzer] = {}
        if not lane_configs:
            # Default 4-way intersection layout
            lane_configs = [
                {"lane_id": "north", "name": "North Approach (Main Ave)"},
                {"lane_id": "south", "name": "South Approach (Main Ave)"},
                {"lane_id": "east", "name": "East Approach (Cross St)"},
                {"lane_id": "west", "name": "West Approach (Cross St)"}
            ]
        for config in lane_configs:
            self.lanes[config["lane_id"]] = LaneTrafficAnalyzer(
                lane_id=config["lane_id"],
                name=config.get("name", ""),
                roi_polygon=config.get("roi_polygon"),
                max_capacity_pcu=config.get("max_capacity_pcu", DEFAULT_MAX_PCU_CAPACITY)
            )

    def process_lane_detections(self, lane_id: str, detections: List[Dict]) -> Dict[str, Any]:
        """Processes detections specifically for a given approach lane."""
        if lane_id in self.lanes:
            return self.lanes[lane_id].analyze(detections)
        return {}

    def get_intersection_snapshot(self) -> Dict[str, Any]:
        """Provides full intersection state across all directions."""
        total_intersection_pcu = 0.0
        total_intersection_vehicles = 0
        emergency_lanes = []
        lane_summaries = {}

        for lane_id, analyzer in self.lanes.items():
            summary = analyzer.get_summary()
            lane_summaries[lane_id] = summary
            total_intersection_pcu += summary["total_pcu"]
            total_intersection_vehicles += summary["total_vehicles"]
            if summary["has_emergency"]:
                emergency_lanes.append(lane_id)

        return {
            "lanes": lane_summaries,
            "total_intersection_vehicles": total_intersection_vehicles,
            "total_intersection_pcu": round(total_intersection_pcu, 2),
            "emergency_lanes": emergency_lanes,
            "emergency_active": len(emergency_lanes) > 0
        }
