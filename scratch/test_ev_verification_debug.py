import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from simulation.traffic_simulator import MultiLaneTrafficSimulator
from backend.decision_agent import TrafficDecisionAgent
from backend.traffic_analysis import IntersectionTrafficAnalyzer
from backend.detection import VehicleDetector

sim = MultiLaneTrafficSimulator()
# Force South to be initially Green
agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
agent.current_lane = "south"
agent.current_phase = "GREEN"
agent.phase_time_remaining = 20.0
agent.phase_allocated_time = 20.0

analyzer = IntersectionTrafficAnalyzer()
detector = VehicleDetector(backend="contour")

print("Initial: Active lane is SOUTH GREEN (20s left)")
print("Now injecting AMBULANCE into NORTH approach...")
sim.inject_emergency_vehicle("north")

dt = 0.04
total_time = 0.0
history = []

for step in range(500): # 20 seconds
    signal_state = agent.get_signal_states()
    sim.update_physics(signal_state, delta_time=dt)

    for lane in sim.lanes:
        frame = sim.render_lane_frame(lane, signal_state["signals"][lane])
        dets = detector.detect(frame, is_synthetic=True)
        analyzer.process_lane_detections(lane, dets)

    snapshot = analyzer.get_intersection_snapshot()
    prev_phase = (agent.current_lane, agent.current_phase)
    agent.tick(dt, snapshot)
    new_phase = (agent.current_lane, agent.current_phase)

    total_time += dt

    if new_phase != prev_phase:
        history.append((round(total_time, 2), f"{prev_phase[0].upper()} {prev_phase[1]} -> {new_phase[0].upper()} {new_phase[1]} (remaining: {round(agent.phase_time_remaining, 1)}s)"))

    # Check if EV still in north
    ev_in_north = any(v.is_emergency for v in sim.vehicles['north'])
    if step % 25 == 0 or not ev_in_north:
        print(f"t={total_time:4.2f}s | Active: {agent.current_lane.upper()} {agent.current_phase:7s} ({agent.phase_time_remaining:4.1f}s left) | EV in North: {ev_in_north} | EV det: {snapshot['emergency_lanes']}")
        if not ev_in_north:
            print(">>> AMBULANCE HAS CLEARED THE INTERSECTION! <<<")
            break

print("\n--- PHASE TRANSITION LOG ---")
for t, event in history:
    print(f"  [{t:5.2f}s] {event}")
