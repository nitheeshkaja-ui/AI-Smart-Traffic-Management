"""
Unit & Integration Tests for Simulation-Only Mode
Tests 4-way intersection simulation, OpenCV vehicle detection,
adaptive signal transitions (Green -> Yellow 3s -> All-Red 2s -> Green),
emergency vehicle priority, control endpoints, and confirms clean removal
of obsolete CCTV / upload functionality.
"""

import unittest
import json
import time

from backend.app import app, VALID_LANES, LANE_DISPLAY_NAMES, simulator, decision_agent, detector


class TestSimulationOnlyMode(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_status_endpoint_returns_simulation_only(self):
        """Verify requirement: System runs exclusively in simulation mode."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["feed_mode"], "simulator")
        self.assertEqual(data["detector_type"], "OpenCV Contour")

        # Verify all 4 simulation approaches exist
        lane_names = data.get("lane_names", {})
        for lane in VALID_LANES:
            self.assertIn(lane, lane_names)
            self.assertEqual(data["lane_sources"][lane], "simulator")

    def test_obsolete_cctv_and_upload_endpoints_removed(self):
        """Verify requirement: CCTV and video upload endpoints are completely removed."""
        # 1. /api/upload_video should not exist (404 or 405 Method Not Allowed by static handler)
        res_upload = self.client.post("/api/upload_video", data={})
        self.assertIn(res_upload.status_code, [404, 405])

        # 2. /api/set_source should not exist
        res_source = self.client.post("/api/set_source", json={"lane": "north", "source": "video"})
        self.assertIn(res_source.status_code, [404, 405])

        # 3. /api/set_feed_mode should not exist
        res_mode = self.client.post("/api/set_feed_mode", json={"mode": "cctv"})
        self.assertIn(res_mode.status_code, [404, 405])

    def test_simulation_stream_endpoints(self):
        """Verify simulation stream endpoints are accessible for all 4 lanes."""
        for lane in VALID_LANES:
            res = self.client.get(f"/simulation_feed/{lane}")
            self.assertEqual(res.status_code, 200)
            self.assertIn("multipart/x-mixed-replace", res.content_type)

        # Invalid lane rejected
        res_invalid = self.client.get("/simulation_feed/highway_5")
        self.assertEqual(res_invalid.status_code, 400)

    def test_control_api_actions(self):
        """Verify dashboard interactive control actions in simulation mode."""
        # 1. Mode change
        res_mode = self.client.post("/api/control", json={"action": "set_mode", "mode": "FIXED_TIME"})
        self.assertEqual(res_mode.status_code, 200)
        self.assertEqual(decision_agent.mode, "FIXED_TIME")

        # 2. Force Green
        res_green = self.client.post("/api/control", json={"action": "manual_green", "lane": "south"})
        self.assertEqual(res_green.status_code, 200)

        # 3. Inject Emergency Vehicle
        res_ev = self.client.post("/api/control", json={"action": "inject_emergency", "lane": "east"})
        self.assertEqual(res_ev.status_code, 200)
        # Verify emergency vehicle injected
        has_ev = any(v.is_emergency for v in simulator.vehicles["east"])
        self.assertTrue(has_ev)

        # 4. Set Traffic Level (Rush hour)
        res_traffic = self.client.post("/api/control", json={"action": "set_traffic_level", "lane": "north", "level": "rush_hour"})
        self.assertEqual(res_traffic.status_code, 200)
        self.assertEqual(simulator.lane_traffic_levels["north"], "rush_hour")

        # Restore auto mode
        self.client.post("/api/control", json={"action": "set_mode", "mode": "AUTO_ADAPTIVE"})

    def test_yellow_and_all_red_durations(self):
        """Verify requirement: Yellow is 3s, All-Red is 2s."""
        self.assertEqual(decision_agent.yellow_duration, 3)
        self.assertEqual(decision_agent.all_red_duration, 2)

    def test_opencv_contour_detector_simulation(self):
        """Verify OpenCV vehicle detection works on simulation frames."""
        frame = simulator.render_lane_frame("north", {"color": "GREEN", "seconds_left": 15})
        self.assertEqual(frame.shape[:2], (480, 640))
        dets = detector.detect(frame, is_synthetic=True)
        self.assertIsInstance(dets, list)


if __name__ == "__main__":
    unittest.main()
