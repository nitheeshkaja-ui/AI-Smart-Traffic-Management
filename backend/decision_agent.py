"""
AI-Based Smart Traffic Management System
Module: Intelligent Decision Agent (Adaptive Signal Timing & Emergency Priority)
"""

import time
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("decision_agent")

PHASE_GREEN = "GREEN"
PHASE_YELLOW = "YELLOW"
PHASE_ALL_RED = "ALL_RED"

MODE_AUTO = "AUTO_ADAPTIVE"
MODE_FIXED = "FIXED_TIME"
MODE_MANUAL = "MANUAL_OVERRIDE"


class TrafficDecisionAgent:
    """
    Intelligent Adaptive Traffic Signal Controller.
    Dynamically allocates green signal timings based on real-time PCU traffic density,
    guarantees Emergency Vehicle Priority Overrides (EVPO), and prevents lane starvation.
    """

    def __init__(
        self,
        lane_ids: Optional[List[str]] = None,
        min_green: int = 10,
        max_green: int = 50,
        yellow_duration: int = 3,
        all_red_duration: int = 2,
        starvation_limit: int = 90,
        fixed_green_duration: int = 20
    ):
        self.lane_ids = lane_ids or ["north", "south", "east", "west"]
        self.min_green = min_green
        self.max_green = max_green
        self.yellow_duration = yellow_duration
        self.all_red_duration = all_red_duration
        self.starvation_limit = starvation_limit
        self.fixed_green_duration = fixed_green_duration

        self.mode = MODE_AUTO

        # State machine
        self.current_lane_idx = 0
        self.current_lane = self.lane_ids[0]
        self.current_phase = PHASE_GREEN
        self.phase_allocated_time = self.min_green
        self.phase_time_remaining = self.min_green
        self.last_tick_time = time.time()

        # Starvation tracking (seconds since last green)
        self.lane_wait_times = {lane: 0.0 for lane in self.lane_ids}

        # Emergency override tracking
        self.emergency_override_active = False
        self.emergency_lane: Optional[str] = None
        self.manual_override_lane: Optional[str] = None

        # Statistics & Performance Metrics for Capstone evaluation
        self.total_cycles_completed = 0
        self.emergency_overrides_handled = 0
        self.estimated_wait_time_saved_sec = 0.0
        self.history_logs: List[Dict[str, Any]] = []

    def set_mode(self, mode: str):
        """Sets operating mode: AUTO_ADAPTIVE, FIXED_TIME, or MANUAL_OVERRIDE."""
        if mode in [MODE_AUTO, MODE_FIXED, MODE_MANUAL]:
            self.mode = mode
            logger.info("Operating mode changed to: %s", mode)

    def manual_override(self, lane_id: str):
        """Allows manual operator override to force green on a specific approach."""
        if lane_id in self.lane_ids:
            self.mode = MODE_MANUAL
            self.manual_override_lane = lane_id
            self._transition_to_lane(lane_id, duration=30)

    def calculate_green_time(self, lane_pcu: float, total_intersection_pcu: float) -> int:
        """
        Calculates optimal green time proportional to lane PCU density.
        Formula: T_green = T_min + (Lane_PCU / Total_PCU) * (T_max - T_min)
        Clamped to ensure waiting approaches do not exceed the starvation limit.
        """
        if total_intersection_pcu <= 0.0 or lane_pcu <= 0.0:
            return self.min_green

        ratio = lane_pcu / max(total_intersection_pcu, 1.0)
        dynamic_green = self.min_green + int(ratio * (self.max_green - self.min_green))

        # Clamp green time to preserve headroom for waiting lanes approaching the starvation limit
        max_waiting_time = max(
            (w for l, w in self.lane_wait_times.items() if l != self.current_lane),
            default=0.0
        )
        time_to_starvation = max(
            float(self.min_green),
            self.starvation_limit - max_waiting_time - self.yellow_duration - self.all_red_duration - 2.0
        )
        safe_max_green = max(self.min_green, min(int(time_to_starvation), self.max_green))
        return max(self.min_green, min(dynamic_green, safe_max_green))

    def _select_next_lane(self, lane_summaries: Dict[str, Any]) -> str:
        """
        Selects next lane to receive green signal based on:
        1. Emergency Vehicle presence (Highest Priority).
        2. Starvation prevention (Anti-starvation override).
        3. Dynamic PCU density ranking.
        """
        # 1. Emergency vehicle check (Highest Priority)
        for lane_id, summary in lane_summaries.items():
            if summary.get("has_emergency", False):
                return lane_id

        # 2. Check for starving lanes (waited >= starvation threshold)
        # Threshold accounts for min_phase (15s) + buffer so any waiting approach receives green <= 90s
        starvation_trigger = max(10.0, self.starvation_limit - (self.min_green + self.yellow_duration + self.all_red_duration) - 5.0)
        starving_lanes = [
            lane for lane, wait in self.lane_wait_times.items()
            if wait >= starvation_trigger and lane != self.current_lane
        ]
        if starving_lanes:
            # Pick the lane waiting longest among starving ones
            chosen = max(starving_lanes, key=lambda l: self.lane_wait_times[l])
            self._log_event(f"Anti-Starvation priority granted to {chosen.upper()} (waited {round(self.lane_wait_times[chosen], 1)}s)")
            return chosen

        # 3. Dynamic density selection: pick non-current lane with highest PCU
        candidate_lanes = [l for l in self.lane_ids if l != self.current_lane]
        if candidate_lanes:
            best_lane = max(
                candidate_lanes,
                key=lambda l: lane_summaries.get(l, {}).get("total_pcu", 0.0)
            )
            # If all candidates have 0 traffic, fall back to round-robin
            if lane_summaries.get(best_lane, {}).get("total_pcu", 0.0) == 0.0:
                next_idx = (self.current_lane_idx + 1) % len(self.lane_ids)
                return self.lane_ids[next_idx]
            return best_lane

        return self.lane_ids[0]

    def _transition_to_lane(self, target_lane: str, duration: int):
        """Immediately sets green for a specified lane."""
        self.current_lane = target_lane
        self.current_lane_idx = self.lane_ids.index(target_lane) if target_lane in self.lane_ids else 0
        self.current_phase = PHASE_GREEN
        self.phase_allocated_time = duration
        self.phase_time_remaining = duration
        self.lane_wait_times[target_lane] = 0.0

    def tick(self, delta_time: float, intersection_snapshot: Dict[str, Any]):
        """
        State machine clock step. Called every frame or tick interval.
        Updates signal phases, timers, starvation counters, and handles overrides.
        """
        self.phase_time_remaining -= delta_time
        lane_summaries = intersection_snapshot.get("lanes", {})
        total_pcu = intersection_snapshot.get("total_intersection_pcu", 0.0)
        emergency_lanes = intersection_snapshot.get("emergency_lanes", [])

        # Update wait times for non-green lanes
        for lane in self.lane_ids:
            if lane != self.current_lane:
                self.lane_wait_times[lane] += delta_time
            else:
                self.lane_wait_times[lane] = 0.0

        # --- Emergency Vehicle Priority Override Logic ---
        if emergency_lanes and self.mode != MODE_MANUAL:
            target_ev_lane = emergency_lanes[0]
            if self.current_lane == target_ev_lane:
                # Emergency vehicle is already on the green approach: keep green corridor open!
                if self.current_phase == PHASE_GREEN:
                    if self.phase_time_remaining < 6.0:
                        self.phase_time_remaining = 10.0
                self.emergency_override_active = True
                self.emergency_lane = target_ev_lane
            else:
                # Emergency vehicle is in another lane waiting for green!
                # Safe rapid clearance: transition active green to 3s Yellow
                if self.current_phase == PHASE_GREEN:
                    self.current_phase = PHASE_YELLOW
                    self.phase_allocated_time = self.yellow_duration
                    self.phase_time_remaining = float(self.yellow_duration)  # Safe rapid clearance
                    self.emergency_override_active = True
                    self.emergency_lane = target_ev_lane
                    self.emergency_overrides_handled += 1
                    self.estimated_wait_time_saved_sec += 25.0
                    self._log_event(f"Emergency Priority Triggered for {target_ev_lane.upper()}")
                else:
                    # Signal is already in Yellow or All-Red transition: ensure priority targets the EV approach
                    self.emergency_override_active = True
                    self.emergency_lane = target_ev_lane
        else:
            self.emergency_override_active = False
            self.emergency_lane = None

        # --- Anti-Starvation Preemptive Clearance Logic ---
        # If any waiting lane is within Yellow + All-Red buffer of the starvation limit,
        # initiate Yellow clearance so the starving approach receives GREEN within 90 seconds.
        if (
            self.current_phase == PHASE_GREEN
            and self.phase_time_remaining > (self.yellow_duration + self.all_red_duration)
            and not self.emergency_override_active
            and self.mode != MODE_MANUAL
        ):
            starvation_trigger = max(10.0, self.starvation_limit - self.yellow_duration - self.all_red_duration - 2.0)
            starving_candidates = [
                l for l, w in self.lane_wait_times.items()
                if w >= starvation_trigger and l != self.current_lane
            ]
            if starving_candidates:
                starving_target = max(starving_candidates, key=lambda l: self.lane_wait_times[l])
                self.current_phase = PHASE_YELLOW
                self.phase_allocated_time = self.yellow_duration
                self.phase_time_remaining = float(self.yellow_duration)
                self._log_event(f"Anti-Starvation clearance initiated for {starving_target.upper()} (waited {round(self.lane_wait_times[starving_target], 1)}s)")

        # --- Phase Transitions ---
        if self.phase_time_remaining <= 0.0:
            if self.current_phase == PHASE_GREEN:
                # Green -> Yellow clearance
                self.current_phase = PHASE_YELLOW
                self.phase_allocated_time = self.yellow_duration
                self.phase_time_remaining = self.yellow_duration

            elif self.current_phase == PHASE_YELLOW:
                # Yellow -> All Red safety buffer
                self.current_phase = PHASE_ALL_RED
                self.phase_allocated_time = self.all_red_duration
                self.phase_time_remaining = self.all_red_duration

            elif self.current_phase == PHASE_ALL_RED:
                # All Red -> Green for next lane
                self.total_cycles_completed += 1

                if self.mode == MODE_FIXED:
                    # Round robin fixed duration (default 20s)
                    self.current_lane_idx = (self.current_lane_idx + 1) % len(self.lane_ids)
                    self.current_lane = self.lane_ids[self.current_lane_idx]
                    allocated = self.fixed_green_duration
                elif self.emergency_override_active and self.emergency_lane:
                    # Switch directly to emergency lane
                    self.current_lane = self.emergency_lane
                    self.current_lane_idx = self.lane_ids.index(self.emergency_lane)
                    allocated = 20
                else:
                    # Dynamic AI decision
                    next_lane = self._select_next_lane(lane_summaries)
                    self.current_lane = next_lane
                    self.current_lane_idx = self.lane_ids.index(next_lane)

                    target_pcu = lane_summaries.get(next_lane, {}).get("total_pcu", 0.0)
                    allocated = self.calculate_green_time(target_pcu, total_pcu)

                    # Dynamic vs Fixed saving estimation:
                    # If adaptive allocates less to empty lanes, time is saved
                    self.estimated_wait_time_saved_sec += max(0, 25 - allocated)

                self.current_phase = PHASE_GREEN
                self.phase_allocated_time = allocated
                self.phase_time_remaining = allocated
                self.lane_wait_times[self.current_lane] = 0.0

                self._log_event(f"Green Signal granted to {self.current_lane.upper()} ({allocated}s)")

    def _log_event(self, message: str):
        """Keeps a small sliding log of system decisions."""
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "lane": self.current_lane,
            "message": message
        }
        self.history_logs.append(entry)
        if len(self.history_logs) > 30:
            self.history_logs.pop(0)

    def get_signal_states(self) -> Dict[str, Any]:
        """
        Returns traffic light colors and remaining time for each intersection lane.
        """
        signals = {}
        for lane in self.lane_ids:
            if lane == self.current_lane:
                signals[lane] = {
                    "color": self.current_phase,
                    "seconds_left": max(0, int(round(self.phase_time_remaining)))
                }
            else:
                signals[lane] = {
                    "color": "RED",
                    "seconds_left": max(0, int(round(self.phase_time_remaining)))
                }

        return {
            "mode": self.mode,
            "current_lane": self.current_lane,
            "current_phase": self.current_phase,
            "phase_time_remaining": max(0, int(round(self.phase_time_remaining))),
            "phase_allocated_time": self.phase_allocated_time,
            "emergency_override_active": self.emergency_override_active,
            "emergency_lane": self.emergency_lane,
            "signals": signals,
            "stats": {
                "cycles_completed": self.total_cycles_completed,
                "emergency_overrides": self.emergency_overrides_handled,
                "wait_time_saved_sec": round(self.estimated_wait_time_saved_sec, 1)
            },
            "recent_events": self.history_logs[-8:]
        }
