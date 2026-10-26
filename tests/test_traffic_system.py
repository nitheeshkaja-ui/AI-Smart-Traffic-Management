"""
AI-Based Smart Traffic Management System
Unit & Integration Test Suite
"""

import unittest
import numpy as np
import time

from backend.detection import VehicleDetector, COCO_VEHICLE_CLASSES
from backend.traffic_analysis import LaneTrafficAnalyzer, IntersectionTrafficAnalyzer
from backend.decision_agent import TrafficDecisionAgent, PHASE_GREEN, PHASE_YELLOW, PHASE_ALL_RED
from simulation.traffic_simulator import MultiLaneTrafficSimulator


class TestVehicleDetector(unittest.TestCase):
    def setUp(self):
        self.detector = VehicleDetector(backend="contour")

    def test_detector_initialization(self):
        self.assertIsNotNone(self.detector)

    def test_detect_blank_frame(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = self.detector.detect(frame)
        self.assertIsInstance(detections, list)

    def test_draw_annotations(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_dets = [{
            "bbox": [100, 100, 200, 200],
            "class_name": "car",
            "confidence": 0.88,
            "center": (150, 150),
            "is_emergency": False
        }]
        annotated = self.detector.draw_annotations(frame, mock_dets, header_text="TEST FEED")
        self.assertEqual(annotated.shape, frame.shape)

    def test_coco_vehicle_classes_mapping(self):
        expected_classes = {
            1: "bicycle",
            2: "car",
            3: "motorcycle",
            5: "bus",
            7: "truck"
        }
        for class_id, expected_name in expected_classes.items():
            self.assertIn(class_id, COCO_VEHICLE_CLASSES)
            self.assertEqual(COCO_VEHICLE_CLASSES[class_id], expected_name)

    def test_detector_fallback_on_missing_model(self):
        fallback_detector = VehicleDetector(backend="auto", model_path="models/nonexistent_file.pt")
        self.assertEqual(fallback_detector.backend_type, "contour")

    def test_yolo_detection_format(self):
        # When YOLO is available in venv, verify output structure
        detector = VehicleDetector(backend="auto")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dets = detector.detect(frame)
        self.assertIsInstance(dets, list)

    def test_detector_source_type_selection(self):
        detector = VehicleDetector(backend="auto")
        # Blank/black frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Synthetic source route
        synthetic_dets = detector.detect(frame, is_synthetic=True)
        self.assertIsInstance(synthetic_dets, list)
        # Real-world source route
        real_dets = detector.detect(frame, is_synthetic=False)
        self.assertIsInstance(real_dets, list)


class TestTrafficAnalysis(unittest.TestCase):
    def setUp(self):
        self.analyzer = LaneTrafficAnalyzer(lane_id="north", name="North Approach")

    def test_pcu_calculation(self):
        mock_dets = [
            {"center": (100, 100), "class_name": "car", "is_emergency": False},
            {"center": (120, 120), "class_name": "car", "is_emergency": False},
            {"center": (140, 140), "class_name": "bus", "is_emergency": False},       # 2.5 PCU
            {"center": (160, 160), "class_name": "motorcycle", "is_emergency": False} # 0.5 PCU
        ]
        summary = self.analyzer.analyze(mock_dets)
        # 1.0 + 1.0 + 2.5 + 0.5 = 5.0 PCU
        self.assertEqual(summary["total_vehicles"], 4)
        self.assertAlmostEqual(summary["total_pcu"], 5.0, places=1)
        self.assertFalse(summary["has_emergency"])

    def test_emergency_detection_in_analysis(self):
        mock_dets = [
            {"center": (100, 100), "class_name": "ambulance", "is_emergency": True}
        ]
        summary = self.analyzer.analyze(mock_dets)
        self.assertTrue(summary["has_emergency"])
        self.assertEqual(summary["emergency_count"], 1)

    def test_intersection_analyzer(self):
        intersection = IntersectionTrafficAnalyzer()
        self.assertIn("north", intersection.lanes)
        self.assertIn("south", intersection.lanes)
        self.assertIn("east", intersection.lanes)
        self.assertIn("west", intersection.lanes)

        mock_north = [{"center": (50, 50), "class_name": "car", "is_emergency": False}]
        intersection.process_lane_detections("north", mock_north)
        snapshot = intersection.get_intersection_snapshot()
        self.assertEqual(snapshot["total_intersection_vehicles"], 1)


class TestDecisionAgent(unittest.TestCase):
    def setUp(self):
        self.agent = TrafficDecisionAgent(
            lane_ids=["north", "south", "east", "west"],
            min_green=10,
            max_green=50,
            yellow_duration=3,
            all_red_duration=1
        )

    def test_dynamic_green_calculation(self):
        # High density lane (15 PCU out of 20 Total PCU)
        green_time = self.agent.calculate_green_time(lane_pcu=15.0, total_intersection_pcu=20.0)
        self.assertGreater(green_time, self.agent.min_green)
        self.assertLessEqual(green_time, self.agent.max_green)

        # Empty lane
        min_time = self.agent.calculate_green_time(lane_pcu=0.0, total_intersection_pcu=20.0)
        self.assertEqual(min_time, self.agent.min_green)

    def test_phase_transition_cycle(self):
        # Step through Green -> Yellow -> All Red -> Green
        self.agent.phase_time_remaining = 0.5
        snapshot = {"lanes": {}, "total_intersection_pcu": 10.0, "emergency_lanes": []}

        # Step into Yellow
        self.agent.tick(0.6, snapshot)
        self.assertEqual(self.agent.current_phase, PHASE_YELLOW)

        # Step into All Red
        self.agent.phase_time_remaining = 0.1
        self.agent.tick(0.2, snapshot)
        self.assertEqual(self.agent.current_phase, PHASE_ALL_RED)

        # Step into next Green
        self.agent.phase_time_remaining = 0.1
        self.agent.tick(0.2, snapshot)
        self.assertEqual(self.agent.current_phase, PHASE_GREEN)

    def test_emergency_priority_override(self):
        # Start on North Green
        self.agent.current_lane = "north"
        self.agent.current_phase = PHASE_GREEN
        self.agent.phase_time_remaining = 25.0

        # Ambulance appears on East approach!
        snapshot = {
            "lanes": {"east": {"total_pcu": 5.0, "has_emergency": True}},
            "total_intersection_pcu": 10.0,
            "emergency_lanes": ["east"]
        }
        self.agent.tick(0.1, snapshot)

        # North should be switched to rapid Yellow to clear corridor for East
        self.assertTrue(self.agent.emergency_override_active)
        self.assertEqual(self.agent.emergency_lane, "east")
        self.assertEqual(self.agent.current_phase, PHASE_YELLOW)

    def test_emergency_priority_sequence_all_four_directions(self):
        """Verifies full GREEN -> YELLOW (3s) -> ALL_RED (2s) -> EV GREEN for North, South, East, West."""
        for target_lane in ["north", "south", "east", "west"]:
            conflicting_lane = "south" if target_lane != "south" else "north"
            agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
            agent.current_lane = conflicting_lane
            agent.current_phase = PHASE_GREEN
            agent.phase_time_remaining = 25.0

            # Ambulance appears on target lane
            snapshot = {
                "lanes": {target_lane: {"total_pcu": 3.5, "has_emergency": True}},
                "total_intersection_pcu": 8.0,
                "emergency_lanes": [target_lane]
            }

            # Step into tick: conflicting lane must immediately transition to YELLOW (3s)
            agent.tick(0.04, snapshot)
            self.assertEqual(agent.current_lane, conflicting_lane)
            self.assertEqual(agent.current_phase, PHASE_YELLOW)
            self.assertEqual(agent.emergency_lane, target_lane)
            self.assertTrue(agent.emergency_override_active)

            # Advance through remaining 3.0s of YELLOW
            agent.tick(3.0, snapshot)
            self.assertEqual(agent.current_phase, PHASE_ALL_RED)

            # Advance through 2.0s of ALL_RED
            agent.tick(2.0, snapshot)
            self.assertEqual(agent.current_phase, PHASE_GREEN)
            self.assertEqual(agent.current_lane, target_lane, f"Emergency priority failed to grant green to {target_lane}")
            self.assertEqual(agent.phase_allocated_time, 20)

    def test_ordinary_red_cars_do_not_trigger_emergency(self):
        """Verifies that non-emergency vehicle frames with red colors do not trigger false emergency flags."""
        detector = VehicleDetector(backend="contour")
        sim = MultiLaneTrafficSimulator()
        for lane in ["north", "south", "east", "west"]:
            frame = sim.render_lane_frame(lane, {"color": "RED", "seconds_left": 10})
            dets = detector.detect(frame, is_synthetic=True)
            ev_dets = [d for d in dets if d.get("is_emergency", False)]
            self.assertEqual(len(ev_dets), 0, f"False positive emergency detection in {lane}!")

    def test_normal_adaptive_resumes_after_emergency(self):
        """Verifies that normal PCU-based adaptive control resumes once emergency clears without endless switching."""
        agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
        agent.current_lane = "north"
        agent.current_phase = PHASE_GREEN
        agent.phase_allocated_time = 20
        agent.phase_time_remaining = 20.0
        agent.emergency_override_active = True
        agent.emergency_lane = "north"

        # Emergency clears from intersection snapshot
        normal_snapshot = {
            "lanes": {
                "north": {"total_pcu": 1.0, "has_emergency": False},
                "south": {"total_pcu": 12.0, "has_emergency": False},
                "east": {"total_pcu": 2.0, "has_emergency": False},
                "west": {"total_pcu": 3.0, "has_emergency": False}
            },
            "total_intersection_pcu": 18.0,
            "emergency_lanes": []
        }

        # Tick once: override flags must clear
        agent.tick(0.04, normal_snapshot)
        self.assertFalse(agent.emergency_override_active)
        self.assertIsNone(agent.emergency_lane)

        # Advance through remaining green
        agent.tick(20.0, normal_snapshot)
        self.assertEqual(agent.current_phase, PHASE_YELLOW)

        # Advance through yellow (3s)
        agent.tick(3.0, normal_snapshot)
        self.assertEqual(agent.current_phase, PHASE_ALL_RED)

        # Advance through all-red (2s): must pick highest PCU lane (south has 12 PCU)
        agent.tick(2.0, normal_snapshot)
        self.assertEqual(agent.current_phase, PHASE_GREEN)
        self.assertEqual(agent.current_lane, "south", "Adaptive AI should select South as it has the highest PCU density")

    def test_anti_starvation_threshold_enforced(self):
        """Verifies that waiting lanes nearing 90s starvation limit trigger clearance and receive green."""
        agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2, starvation_limit=90)
        agent.current_lane = "north"
        agent.current_phase = PHASE_GREEN
        agent.phase_allocated_time = 40
        agent.phase_time_remaining = 35.0

        # East has waited 84.0s
        agent.lane_wait_times = {"north": 0.0, "south": 10.0, "east": 84.0, "west": 10.0}
        snapshot = {
            "lanes": {l: {"total_pcu": 10.0 if l == "north" else 1.0, "has_emergency": False} for l in agent.lane_ids},
            "total_intersection_pcu": 13.0,
            "emergency_lanes": []
        }

        # Step tick: must initiate yellow clearance to serve East within 90s
        agent.tick(0.05, snapshot)
        self.assertEqual(agent.current_phase, PHASE_YELLOW)

        # Advance 3s Yellow + 2s All-Red
        agent.tick(3.0, snapshot)
        self.assertEqual(agent.current_phase, PHASE_ALL_RED)
        agent.tick(2.0, snapshot)

        # East must receive green
        self.assertEqual(agent.current_phase, PHASE_GREEN)
        self.assertEqual(agent.current_lane, "east")
        self.assertLessEqual(agent.lane_wait_times["east"], 90.0)

    def test_no_consecutive_green_phases_for_heavy_lane(self):
        """Verifies that a heavy traffic lane never receives back-to-back green phases."""
        agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
        agent.current_lane = "north"
        agent.current_phase = PHASE_ALL_RED
        agent.phase_time_remaining = 0.0

        # North has massive PCU density (25 PCU vs 1 PCU in other lanes)
        snapshot = {
            "lanes": {
                "north": {"total_pcu": 25.0, "has_emergency": False},
                "south": {"total_pcu": 2.0, "has_emergency": False},
                "east": {"total_pcu": 1.0, "has_emergency": False},
                "west": {"total_pcu": 1.0, "has_emergency": False}
            },
            "total_intersection_pcu": 29.0,
            "emergency_lanes": []
        }

        agent.tick(0.05, snapshot)
        # Even with 25 PCU, North cannot be chosen consecutively; South (highest among other candidates) is selected
        self.assertNotEqual(agent.current_lane, "north")
        self.assertEqual(agent.current_phase, PHASE_GREEN)


class TestTrafficSimulator(unittest.TestCase):
    def test_simulator_render(self):
        sim = MultiLaneTrafficSimulator(width=320, height=240)
        frame = sim.render_lane_frame("north", {"color": "GREEN", "seconds_left": 15})
        self.assertEqual(frame.shape, (240, 320, 3))

    def test_time_based_vehicle_movement(self):
        sim = MultiLaneTrafficSimulator(width=320, height=240)
        # Ensure north has at least one vehicle past the stop line moving on green
        sim.vehicles["north"][0].y_pos = 100.0  # past stop line (130)
        initial_y = sim.vehicles["north"][0].y_pos
        speed = sim.vehicles["north"][0].speed
        signals = {"signals": {"north": {"color": "GREEN"}}}

        # Advance physics by 0.04s (1 frame at 25 FPS)
        sim.update_physics(signals, delta_time=0.04)
        new_y = sim.vehicles["north"][0].y_pos
        self.assertLess(new_y, initial_y, "Vehicle should move forward on green")

    def test_delta_time_clamping_prevents_jumping(self):
        sim = MultiLaneTrafficSimulator(width=320, height=240)
        sim.vehicles["north"][0].y_pos = 100.0
        initial_y = sim.vehicles["north"][0].y_pos
        speed = sim.vehicles["north"][0].speed
        signals = {"signals": {"north": {"color": "GREEN"}}}

        # Simulate a 10-second freeze/pause
        sim.update_physics(signals, delta_time=10.0)
        new_y = sim.vehicles["north"][0].y_pos

        # With clamping to 0.1s max dt, max movement should be speed * 25 * 0.1 * 1.6
        max_allowed_jump = speed * 25.0 * 0.1 * 1.6 + 1.0
        actual_jump = initial_y - new_y
        self.assertLessEqual(actual_jump, max_allowed_jump, "Excessive jump should be clamped")


if __name__ == "__main__":
    unittest.main()
