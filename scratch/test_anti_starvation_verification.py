"""
Complete Anti-Starvation Verification Suite
Simulates 180+ seconds of live intersection traffic and validates all 10 scenarios:
1. Heavy traffic in NORTH (rush_hour), low in SOUTH/EAST/WEST (low).
2. NORTH does not receive unlimited consecutive green phases.
3. Every waiting lane receives green within the 90s starvation threshold.
4. All four directions tested as low-volume waiting lanes.
5. PCU-based adaptive selection active when no lane is starving.
6. Emergency vehicle priority overrides anti-starvation safely.
7. Yellow (3s) and All-Red (2s) transitions preserved.
8. 180+ seconds simulated time run.
9. Maximum waiting time per lane recorded.
10. Cycle stability verified (no endless switching or starvation).
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from simulation.traffic_simulator import MultiLaneTrafficSimulator
from backend.decision_agent import TrafficDecisionAgent
from backend.traffic_analysis import IntersectionTrafficAnalyzer
from backend.detection import VehicleDetector

def run_180s_anti_starvation_simulation():
    print("=" * 80)
    print("       SCENARIOS 1, 2, 3, 7, 8, 9, 10: 180-SECOND ANTI-STARVATION TEST        ")
    print("       (NORTH: Heavy Rush Hour Traffic | SOUTH/EAST/WEST: Low Traffic)         ")
    print("=" * 80)

    sim = MultiLaneTrafficSimulator()
    sim.set_traffic_level("north", "rush_hour")
    sim.set_traffic_level("south", "low")
    sim.set_traffic_level("east", "low")
    sim.set_traffic_level("west", "low")

    # Starvation limit configured at 90s, Yellow=3s, All-Red=2s
    agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2, starvation_limit=90)
    analyzer = IntersectionTrafficAnalyzer()
    detector = VehicleDetector(backend="contour")

    dt = 0.05
    total_sim_time = 0.0
    target_sim_time = 185.0

    transitions = []
    consecutive_greens = {l: 0 for l in sim.lanes}
    max_consecutive_greens = {l: 0 for l in sim.lanes}
    last_green_lane = None

    lane_green_counts = {l: 0 for l in sim.lanes}
    max_wait_times = {l: 0.0 for l in sim.lanes}

    last_phase = (agent.current_lane, agent.current_phase)
    phase_start_time = 0.0

    # Verification of Yellow & All-Red durations
    phase_durations = []

    print("[Start] Initializing 180s simulated execution...")

    step = 0
    while total_sim_time < target_sim_time:
        sig_state = agent.get_signal_states()
        sim.update_physics(sig_state, delta_time=dt)

        for lane in sim.lanes:
            frame = sim.render_lane_frame(lane, sig_state["signals"][lane])
            dets = detector.detect(frame, is_synthetic=True)
            analyzer.process_lane_detections(lane, dets)

        snapshot = analyzer.get_intersection_snapshot()
        agent.tick(dt, snapshot)
        total_sim_time += dt
        step += 1

        # Track waiting times
        for l in sim.lanes:
            current_wait = agent.lane_wait_times[l]
            if current_wait > max_wait_times[l]:
                max_wait_times[l] = current_wait

        cur_phase = (agent.current_lane, agent.current_phase)
        if cur_phase != last_phase:
            duration = round(total_sim_time - phase_start_time, 2)
            phase_durations.append((last_phase, duration))
            transitions.append((round(total_sim_time, 2), f"{last_phase[0].upper()} {last_phase[1]} -> {cur_phase[0].upper()} {cur_phase[1]} (previous phase lasted {duration}s)"))

            # Track consecutive green counts
            if cur_phase[1] == "GREEN":
                cur_lane = cur_phase[0]
                lane_green_counts[cur_lane] += 1
                if cur_lane == last_green_lane:
                    consecutive_greens[cur_lane] += 1
                else:
                    consecutive_greens[cur_lane] = 1
                if consecutive_greens[cur_lane] > max_consecutive_greens[cur_lane]:
                    max_consecutive_greens[cur_lane] = consecutive_greens[cur_lane]
                last_green_lane = cur_lane

            last_phase = cur_phase
            phase_start_time = total_sim_time

        if step % 200 == 0:
            print(f"[t={total_sim_time:5.1f}s] Active: {agent.current_lane.upper()} {agent.current_phase:<7s} | Wait times: N={agent.lane_wait_times['north']:.1f}s, S={agent.lane_wait_times['south']:.1f}s, E={agent.lane_wait_times['east']:.1f}s, W={agent.lane_wait_times['west']:.1f}s")

    print("\n--- 180s SIMULATION EXECUTION SUMMARY ---")
    print(f"Total simulated time: {total_sim_time:.1f} seconds")
    print(f"Total cycles completed: {agent.total_cycles_completed}")
    print(f"Green phases granted per lane: {lane_green_counts}")
    print(f"Maximum consecutive green phases: {max_consecutive_greens}")
    print(f"Maximum recorded waiting time per lane:")
    for l in sim.lanes:
        print(f"   {l.upper():5s}: {max_wait_times[l]:.2f}s  (Threshold: 90.0s | Respected: {max_wait_times[l] <= 90.0})")

    # Assertions
    # 1. NORTH does not get unlimited consecutive greens
    assert max_consecutive_greens["north"] == 1, f"NORTH received {max_consecutive_greens['north']} consecutive green phases (expected max 1)!"

    # 2. Every lane received green
    for l in sim.lanes:
        assert lane_green_counts[l] >= 1, f"Lane {l.upper()} received 0 green phases in 180s!"

    # 3. Maximum wait time strictly <= 90.0s
    for l in sim.lanes:
        assert max_wait_times[l] <= 90.0, f"Lane {l.upper()} exceeded 90s starvation threshold! Max wait = {max_wait_times[l]:.2f}s"

    # 4. Yellow (3s) and All-Red (2s) verification
    for (lane, phase), dur in phase_durations:
        if phase == "YELLOW":
            assert abs(dur - 3.0) <= 0.15, f"Yellow phase duration {dur}s differed from 3.0s in {lane}!"
        elif phase == "ALL_RED":
            assert abs(dur - 2.0) <= 0.15, f"All-Red phase duration {dur}s differed from 2.0s in {lane}!"

    print(">>> 180-SECOND SIMULATION ASSERTIONS ALL PASSED <<<")
    return {
        "max_wait_times": max_wait_times,
        "lane_green_counts": lane_green_counts,
        "transitions": transitions,
        "max_consecutive_greens": max_consecutive_greens
    }


def test_individual_low_volume_lanes():
    print("\n" + "=" * 80)
    print("      SCENARIO 4: TESTING ALL FOUR DIRECTIONS AS LOW-VOLUME WAITING LANES      ")
    print("=" * 80)
    for test_lane in ["north", "south", "east", "west"]:
        agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2, starvation_limit=90)
        # Force other lanes to have higher wait times/density, and test_lane to be waiting
        other_lanes = [l for l in agent.lane_ids if l != test_lane]
        active_lane = other_lanes[0]
        agent.current_lane = active_lane
        agent.current_phase = "GREEN"
        agent.phase_time_remaining = 20.0

        # Set test_lane wait time to 86.0s (approaching starvation)
        for l in agent.lane_ids:
            agent.lane_wait_times[l] = 20.0
        agent.lane_wait_times[test_lane] = 86.0
        agent.lane_wait_times[active_lane] = 0.0

        snapshot = {
            "lanes": {l: {"total_pcu": 10.0 if l == active_lane else 1.0, "has_emergency": False} for l in agent.lane_ids},
            "total_intersection_pcu": 13.0,
            "emergency_lanes": []
        }

        # Tick once: active lane must begin Yellow clearance because test_lane is near starvation
        agent.tick(0.05, snapshot)
        assert agent.current_phase == "YELLOW", f"Expected Yellow transition for starving {test_lane}, got {agent.current_phase}"
        
        # Advance through 3.0s Yellow and 2.0s All-Red
        agent.tick(3.0, snapshot)
        assert agent.current_phase == "ALL_RED"
        agent.tick(2.0, snapshot)
        
        # Must grant green to test_lane
        assert agent.current_phase == "GREEN" and agent.current_lane == test_lane, f"Expected {test_lane} to receive green, got {agent.current_lane}"
        print(f"Low-volume lane {test_lane.upper()}: Successfully granted anti-starvation green after {round(agent.lane_wait_times[test_lane], 1)}s wait.")

    print(">>> SCENARIO 4 PASSED: ALL FOUR APPROACHES VERIFIED FOR ANTI-STARVATION <<<")


def test_emergency_overrides_anti_starvation():
    print("\n" + "=" * 80)
    print("   SCENARIO 6: VERIFYING EMERGENCY PRIORITY SAFELY OVERRIDES ANTI-STARVATION    ")
    print("=" * 80)
    agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2, starvation_limit=90)
    agent.current_lane = "north"
    agent.current_phase = "GREEN"
    agent.phase_time_remaining = 15.0

    # East has waited 89 seconds (starving!)
    agent.lane_wait_times["east"] = 89.0
    agent.lane_wait_times["south"] = 40.0
    agent.lane_wait_times["west"] = 40.0
    agent.lane_wait_times["north"] = 0.0

    # But an Ambulance is detected in WEST!
    snapshot = {
        "lanes": {
            "north": {"total_pcu": 5.0, "has_emergency": False},
            "south": {"total_pcu": 2.0, "has_emergency": False},
            "east": {"total_pcu": 1.0, "has_emergency": False},
            "west": {"total_pcu": 3.5, "has_emergency": True}
        },
        "total_intersection_pcu": 11.5,
        "emergency_lanes": ["west"]
    }

    # Tick: Emergency in WEST must be prioritized over starving EAST!
    agent.tick(0.05, snapshot)
    assert agent.emergency_override_active
    assert agent.emergency_lane == "west"
    assert agent.current_phase == "YELLOW"

    # Step through Yellow (3s) and All-Red (2s)
    agent.tick(3.0, snapshot)
    assert agent.current_phase == "ALL_RED"
    agent.tick(2.0, snapshot)

    # WEST receives priority green
    assert agent.current_phase == "GREEN" and agent.current_lane == "west"
    print(f"Emergency Priority Override: WEST (Ambulance) received GREEN even though EAST had waited {agent.lane_wait_times['east']:.1f}s!")

    # Now simulate ambulance clearing WEST
    cleared_snapshot = {
        "lanes": {
            "north": {"total_pcu": 5.0, "has_emergency": False},
            "south": {"total_pcu": 2.0, "has_emergency": False},
            "east": {"total_pcu": 1.0, "has_emergency": False},
            "west": {"total_pcu": 1.0, "has_emergency": False}
        },
        "total_intersection_pcu": 9.0,
        "emergency_lanes": []
    }
    # Tick: Emergency is cleared; because EAST is starving (waited 94s), Yellow clearance is initiated
    agent.tick(0.05, cleared_snapshot)
    assert not agent.emergency_override_active
    assert agent.current_phase == "YELLOW", f"Expected Yellow transition for starving East, got {agent.current_phase}"

    # Advance through Yellow (3s) and All-Red (2s)
    agent.tick(3.0, cleared_snapshot)
    assert agent.current_phase == "ALL_RED"
    agent.tick(2.0, cleared_snapshot)

    # Now starving EAST receives GREEN!
    assert agent.current_phase == "GREEN" and agent.current_lane == "east"
    print(f"Post-Emergency Anti-Starvation: EAST (Starving lane) safely granted GREEN immediately after emergency cleared!")
    print(">>> SCENARIO 6 PASSED: EMERGENCY PRIORITY OVERRIDES AND PRESERVES ANTI-STARVATION <<<")


def test_pcu_adaptive_selection_when_not_starving():
    print("\n" + "=" * 80)
    print("  SCENARIO 5: VERIFYING PCU-BASED ADAPTIVE SELECTION WHEN NO LANE IS STARVING   ")
    print("=" * 80)
    agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2, starvation_limit=90)
    agent.current_lane = "north"
    agent.current_phase = "ALL_RED"
    agent.phase_time_remaining = 0.0

    # No lane is starving: all waits are small (< 30s)
    agent.lane_wait_times = {"north": 0.0, "south": 25.0, "east": 15.0, "west": 10.0}

    # South has highest PCU (15 PCU vs East 4 PCU, West 2 PCU)
    snapshot = {
        "lanes": {
            "north": {"total_pcu": 2.0, "has_emergency": False},
            "south": {"total_pcu": 15.0, "has_emergency": False},
            "east": {"total_pcu": 4.0, "has_emergency": False},
            "west": {"total_pcu": 2.0, "has_emergency": False}
        },
        "total_intersection_pcu": 23.0,
        "emergency_lanes": []
    }

    agent.tick(0.05, snapshot)
    assert agent.current_phase == "GREEN"
    assert agent.current_lane == "south", f"Expected South (highest PCU: 15) to be selected, got {agent.current_lane}"
    assert agent.phase_allocated_time > agent.min_green, f"Expected dynamic green > min_green, got {agent.phase_allocated_time}"
    print(f"PCU Adaptive Selection: SOUTH chosen with {agent.phase_allocated_time}s GREEN (proportional to its 15.0 PCU density).")
    print(">>> SCENARIO 5 PASSED: PCU DENSITY GOVERNS SIGNAL ALLOCATION WHEN UNSTARVED <<<")


if __name__ == "__main__":
    # Run test scenarios
    res_180s = run_180s_anti_starvation_simulation()
    test_individual_low_volume_lanes()
    test_emergency_overrides_anti_starvation()
    test_pcu_adaptive_selection_when_not_starving()

    print("\n" + "=" * 80)
    print("                   ALL ANTI-STARVATION SCENARIOS COMPLETED                      ")
    print("=" * 80)
