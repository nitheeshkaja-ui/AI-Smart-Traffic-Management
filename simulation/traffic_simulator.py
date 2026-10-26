"""
AI-Based Smart Traffic Management System
Module: Traffic Simulation Engine & Video Stream Synthesizer
Generates live realistic multi-lane intersection video streams or loads local video files.
"""

import cv2
import numpy as np
import random
import time
from typing import Dict, List, Optional, Any


class SimulatedVehicle:
    def __init__(self, lane_id: str, v_type: str, y_pos: float, speed: float, is_emergency: bool = False):
        self.lane_id = lane_id
        self.v_type = v_type
        self.y_pos = float(y_pos)
        self.target_speed = float(speed)
        self.current_speed = float(speed)
        self.speed = float(speed)  # backward compatibility alias
        self.is_emergency = is_emergency
        self.strobe_state = 0

        # Dimensions & visual properties
        if v_type == "bus":
            self.width, self.height = 44, 110
            self.color = (30, 160, 230)  # Orange-yellow
        elif v_type == "truck":
            self.width, self.height = 46, 120
            self.color = (180, 100, 40)  # Steel blue
        elif v_type == "motorcycle":
            self.width, self.height = 20, 40
            self.color = (190, 80, 180)  # Purple
        elif is_emergency:
            self.width, self.height = 42, 95
            self.color = (250, 250, 250)  # White body with emergency markings
            self.target_speed = max(self.target_speed, 3.2)
            self.current_speed = self.target_speed
            self.speed = self.target_speed
        else:
            self.width, self.height = 36, 75
            self.color = random.choice([
                (40, 40, 220),   # Vibrant Red
                (50, 180, 80),   # Emerald Green
                (220, 80, 50),   # Royal Blue
                (30, 210, 240),  # Yellow Cab
                (225, 225, 225)  # Silver/White
            ])


class MultiLaneTrafficSimulator:
    """
    Simulates a 4-approach intersection (North, South, East, West).
    Renders realistic moving vehicles, stopping on RED/YELLOW, moving on GREEN,
    and handling emergency vehicle injection.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.lanes = ["north", "south", "east", "west"]
        self.vehicles: Dict[str, List[SimulatedVehicle]] = {l: [] for l in self.lanes}
        self.last_spawn_time = {l: time.perf_counter() for l in self.lanes}
        self.lane_traffic_levels = {
            "north": "normal",
            "south": "normal",
            "east": "normal",
            "west": "normal"
        }
        self.video_captures: Dict[str, Optional[cv2.VideoCapture]] = {l: None for l in self.lanes}

        # Seed initial vehicles
        for lane in self.lanes:
            self._seed_lane(lane)

    def _seed_lane(self, lane: str):
        count = random.randint(2, 3)
        current_y = 165.0
        prev_height = 0
        for i in range(count):
            v_type = random.choices(["car", "motorcycle", "bus", "truck"], weights=[0.6, 0.2, 0.1, 0.1])[0]
            speed = random.uniform(1.4, 2.4)
            veh = SimulatedVehicle(lane, v_type, current_y, speed)
            if i > 0:
                # Add positive spacing based on vehicle heights and buffer to prevent overlap
                gap = random.uniform(22.0, 28.0)
                current_y += (prev_height // 2) + (veh.height // 2) + gap
                veh.y_pos = current_y
            self.vehicles[lane].append(veh)
            prev_height = veh.height

    def set_traffic_level(self, lane: str, level: str):
        """Sets traffic congestion level: low, normal, rush_hour."""
        if lane in self.lanes:
            self.lane_traffic_levels[lane] = level

    def inject_emergency_vehicle(self, lane: str):
        """Spawns an emergency ambulance in the designated approach lane."""
        if lane in self.lanes:
            # Ensure the vehicle entrance corridor is unobstructed for the incoming ambulance
            self.vehicles[lane] = [v for v in self.vehicles[lane] if v.y_pos <= 325.0]
            ambulance = SimulatedVehicle(lane, "ambulance", y_pos=float(self.height - 60), speed=3.2, is_emergency=True)
            self.vehicles[lane].append(ambulance)
            self.vehicles[lane].sort(key=lambda v: v.y_pos)

    def update_physics(self, signal_states: Dict[str, Any], delta_time: float = 0.04):
        """
        Updates vehicle positions based on the active signal phase and elapsed real time.
        Uses clamped delta_time to prevent sudden position jumps.
        """
        # Clamp delta_time between 5ms and 100ms (avoids frozen physics and prevents jumping after pauses)
        dt = max(0.005, min(0.1, delta_time))
        signals = signal_states.get("signals", {})
        now = time.perf_counter()

        for lane in self.lanes:
            lane_signal = signals.get(lane, {}).get("color", "RED")
            vehicles = self.vehicles[lane]

            # 1. Dynamic vehicle spawning with entrance clearance validation
            if self.lane_traffic_levels[lane] == "rush_hour":
                spawn_interval = 1.8
                max_veh = 14
            elif self.lane_traffic_levels[lane] == "low":
                spawn_interval = 12.0
                max_veh = 3
            else:
                spawn_interval = 4.5
                max_veh = 10

            if now - self.last_spawn_time[lane] > spawn_interval:
                rearmost_y = max((v.y_pos for v in vehicles), default=0.0)
                # Only spawn if lane capacity allows and entrance is not blocked by a queue
                if len(vehicles) < max_veh and rearmost_y < (self.height + 25.0):
                    v_type = random.choices(["car", "motorcycle", "bus", "truck"], weights=[0.6, 0.2, 0.1, 0.1])[0]
                    speed = random.uniform(1.4, 2.5)
                    spawn_y = max(float(self.height + 25.0), rearmost_y + 85.0)
                    if spawn_y <= self.height + 100.0:
                        vehicles.append(SimulatedVehicle(lane, v_type, y_pos=spawn_y, speed=speed))
                        self.last_spawn_time[lane] = now

            # 2. Ensure vehicles are strictly sorted by ascending y_pos (nearest to intersection first)
            vehicles.sort(key=lambda v: v.y_pos)

            # 3. Vehicle movement, car-following, braking, and acceleration
            stop_line = 130.0
            for i, v in enumerate(vehicles):
                # Distance to vehicle directly ahead
                dist_ahead = 999.0
                if i > 0:
                    lead_veh = vehicles[i - 1]
                    dist_ahead = v.y_pos - lead_veh.y_pos - (lead_veh.height / 2.0 + v.height / 2.0)
                    # Enforce anti-collision physical buffer: prevent vehicles from overlapping
                    if dist_ahead < 0.0:
                        v.y_pos = lead_veh.y_pos + (lead_veh.height / 2.0 + v.height / 2.0) + 16.0
                        dist_ahead = 16.0

                should_stop = False

                # Stop conditions at traffic signal
                front_y = v.y_pos - v.height / 2.0
                if lane_signal in ["RED", "ALL_RED"]:
                    # Vehicle has not cleared stop line yet
                    if front_y >= (stop_line - 10.0):
                        # Approaching the stop line buffer zone
                        if front_y <= (stop_line + 55.0):
                            should_stop = True

                elif lane_signal == "YELLOW":
                    # Vehicles sufficiently far back must stop; vehicles right at/past stop line clear safely
                    if front_y >= (stop_line + 25.0):
                        if front_y <= (stop_line + 70.0):
                            should_stop = True

                # Car-following gap maintenance
                safe_gap = 18.0
                if dist_ahead < safe_gap:
                    should_stop = True

                # Emergency vehicles clearing green corridors never stop
                if v.is_emergency and lane_signal == "GREEN":
                    should_stop = False

                # 4. Acceleration and deceleration physics
                if should_stop:
                    # Smooth deceleration to complete stop
                    v.current_speed = max(0.0, v.current_speed - 6.0 * dt)
                else:
                    # Accelerate smoothly up to target speed (with green speed boost)
                    desired_speed = v.target_speed * (1.3 if lane_signal == "GREEN" else 1.0)
                    if v.current_speed < desired_speed:
                        v.current_speed = min(desired_speed, v.current_speed + 4.0 * dt)
                    else:
                        v.current_speed = desired_speed

                v.speed = v.current_speed

                # 5. Advance position forward along approach (towards intersection at y=0)
                if v.current_speed > 0.001:
                    step = v.current_speed * (25.0 * dt)
                    v.y_pos -= step

                # Flash emergency strobe at a steady 5 Hz real-time rate
                if v.is_emergency:
                    v.strobe_state = int(now * 10) % 10

            # 6. Remove vehicles that completely crossed through the intersection
            self.vehicles[lane] = [v for v in vehicles if v.y_pos > -100.0]

    def render_lane_frame(self, lane: str, signal_info: Dict[str, Any]) -> np.ndarray:
        """
        Renders a high-resolution top-down perspective road feed for the specified lane approach.
        """
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # 1. Road background (Asphalt dark gray)
        frame[:, :] = (38, 42, 46)

        # Grass borders
        road_left = 180
        road_right = 460
        frame[:, :road_left] = (34, 60, 36)
        frame[:, road_right:] = (34, 60, 36)

        # Sidewalk curbs
        cv2.rectangle(frame, (road_left - 12, 0), (road_left, self.height), (140, 145, 150), -1)
        cv2.rectangle(frame, (road_right, 0), (road_right + 12, self.height), (140, 145, 150), -1)

        # Lane dividers (Dashed yellow/white lines)
        mid_x = (road_left + road_right) // 2
        for y in range(0, self.height, 40):
            cv2.line(frame, (mid_x, y), (mid_x, y + 24), (240, 240, 240), 2)

        # Stop line
        stop_line_y = 120
        cv2.line(frame, (road_left, stop_line_y), (road_right, stop_line_y), (255, 255, 255), 4)
        cv2.putText(frame, "STOP LINE", (road_left + 15, stop_line_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Intersection zone text
        cv2.putText(frame, f"INTERSECTION CROSSING", (road_left + 10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 100, 110), 1)

        # 2. Render Vehicles
        left_lane_x = mid_x - 60
        right_lane_x = mid_x + 60
        vehicles = self.vehicles.get(lane, [])
        for idx, v in enumerate(vehicles):
            vx = left_lane_x if (idx % 2 == 0) else right_lane_x
            vy = int(v.y_pos)

            x1 = vx - v.width // 2
            y1 = vy - v.height // 2
            x2 = vx + v.width // 2
            y2 = vy + v.height // 2

            # Vehicle shadow
            cv2.rectangle(frame, (x1 + 3, y1 + 3), (x2 + 3, y2 + 3), (20, 20, 20), -1)

            # Vehicle body
            cv2.rectangle(frame, (x1, y1), (x2, y2), v.color, -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (20, 20, 20), 1)

            # Windshield & Roof details
            ww = int(v.width * 0.7)
            wx1 = vx - ww // 2
            wx2 = vx + ww // 2
            cv2.rectangle(frame, (wx1, y1 + 10), (wx2, y1 + 22), (60, 60, 60), -1)

            # Headlights
            cv2.circle(frame, (x1 + 6, y1 + 2), 3, (180, 255, 255), -1)
            cv2.circle(frame, (x2 - 6, y1 + 2), 3, (180, 255, 255), -1)

            # Emergency strobe lights & markings
            if v.is_emergency:
                strobe_color = (0, 0, 255) if v.strobe_state < 5 else (255, 0, 0)
                alt_strobe_color = (255, 0, 0) if v.strobe_state < 5 else (0, 0, 255)
                cv2.circle(frame, (vx - 10, vy), 6, strobe_color, -1)
                cv2.circle(frame, (vx + 10, vy), 6, alt_strobe_color, -1)
                # Red Cross emblem
                cv2.line(frame, (vx, vy - 10), (vx, vy + 10), (0, 0, 255), 3)
                cv2.line(frame, (vx - 10, vy), (vx + 10, vy), (0, 0, 255), 3)

        # 3. Approach Name & Signal Status Overlay
        color_name = signal_info.get("color", "RED")
        secs_left = signal_info.get("seconds_left", 0)

        # Traffic light HUD in top right
        signal_color_bgr = (0, 0, 255) if color_name == "RED" else ((0, 255, 255) if color_name == "YELLOW" else (0, 255, 0))
        cv2.rectangle(frame, (self.width - 150, 10), (self.width - 10, 65), (20, 20, 24), -1)
        cv2.circle(frame, (self.width - 125, 38), 16, signal_color_bgr, -1)
        cv2.putText(frame, f"{color_name}", (self.width - 95, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, f"{secs_left}s", (self.width - 95, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        # Lane title top left
        cv2.rectangle(frame, (10, 10), (180, 45), (20, 20, 24), -1)
        cv2.putText(frame, f"CAM: {lane.upper()}", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)

        return frame
