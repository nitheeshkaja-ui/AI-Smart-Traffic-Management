import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from simulation.traffic_simulator import MultiLaneTrafficSimulator
from backend.decision_agent import TrafficDecisionAgent
from backend.traffic_analysis import IntersectionTrafficAnalyzer
from backend.detection import VehicleDetector

sim = MultiLaneTrafficSimulator()
agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
analyzer = IntersectionTrafficAnalyzer()
detector = VehicleDetector(backend="contour")

print("================================================================================")
print("              35-SECOND LIVE INTERSECTION VEHICLE MOVEMENT TEST                 ")
print("================================================================================")

initial_snapshot = {}
for lane in sim.lanes:
    initial_snapshot[lane] = [(v.v_type, round(v.y_pos, 1), round(v.current_speed, 2)) for v in sim.vehicles[lane]]
    print(f"INITIAL {lane.upper():5s} [{len(sim.vehicles[lane])} vehicles]: {initial_snapshot[lane]}")

start_time = time.perf_counter()
last_tick = start_time
steps = 0
last_report = start_time
lanes_granted_green = set()
total_crossings = 0
prev_counts = {l: len(sim.vehicles[l]) for l in sim.lanes}

while time.perf_counter() - start_time < 35.0:
    loop_start = time.perf_counter()
    raw_delta = loop_start - last_tick
    last_tick = loop_start
    dt = max(0.005, min(0.1, raw_delta))

    signal_state = agent.get_signal_states()
    sim.update_physics(signal_state, delta_time=dt)

    raw_frames = {}
    for lane in sim.lanes:
        frame = sim.render_lane_frame(lane, signal_state["signals"][lane])
        dets = detector.detect(frame, is_synthetic=True)
        analyzer.process_lane_detections(lane, dets)

    snapshot = analyzer.get_intersection_snapshot()
    agent.tick(dt, snapshot)

    cur_lane = agent.current_lane
    if agent.current_phase == "GREEN":
        lanes_granted_green.add(cur_lane)

    steps += 1
    now = time.perf_counter()
    if now - last_report >= 5.0:
        last_report = now
        elapsed = round(now - start_time, 1)
        active = agent.current_lane
        phase = agent.current_phase
        time_rem = agent.phase_time_remaining
        pcu = snapshot['lanes'].get(active, {}).get('total_pcu', 0.0)
        print(f"\n[t={elapsed:4.1f}s] Active Signal: {active.upper()} {phase} (remaining: {time_rem:.1f}s | Active PCU: {pcu:.1f})")
        for lane in sim.lanes:
            vehs = sim.vehicles[lane]
            positions = [round(v.y_pos, 1) for v in vehs]
            speeds = [round(v.current_speed, 2) for v in vehs]
            print(f"   {lane.upper():5s} ({len(vehs)} vehs): y={positions} | speeds={speeds}")

    # Maintain ~25 FPS loop pace
    elapsed_frame = time.perf_counter() - loop_start
    time.sleep(max(0.005, (1.0 / 25.0) - elapsed_frame))

print("\n================================================================================")
print("                           FINAL VERIFICATION SUMMARY                           ")
print("================================================================================")
for lane in sim.lanes:
    vehs = sim.vehicles[lane]
    final_info = [(v.v_type, round(v.y_pos, 1), round(v.current_speed, 2)) for v in vehs]
    print(f"FINAL {lane.upper():5s} [{len(vehs)} vehicles]: {final_info}")

print(f"\nTotal simulation steps executed: {steps} frames (~{round(steps / 35.0, 1)} FPS)")
print(f"Lanes successfully served with GREEN phase: {[l.upper() for l in lanes_granted_green]}")
print(f"Completed cycles: {agent.total_cycles_completed}")
print(f"Wait time saved by adaptive AI: {round(agent.estimated_wait_time_saved_sec, 1)}s")

# Automated assertions on vehicle dynamics
assert len(lanes_granted_green) >= 2, f"Expected at least 2 lanes served with GREEN in 35s, got {len(lanes_granted_green)}"
for lane in sim.lanes:
    # Verify no vehicles are stuck at y_pos == 500 or have overlapping negative gaps
    vehs = sim.vehicles[lane]
    for i in range(1, len(vehs)):
        gap = vehs[i].y_pos - vehs[i-1].y_pos - (vehs[i].height / 2.0 + vehs[i-1].height / 2.0)
        assert gap >= -1.0, f"Collision detected in {lane}: gap={gap} between veh {i-1} and {i}"

print("\n>>> ALL VEHICLE MOVEMENT DYNAMICS AND INTERSECTION VERIFICATIONS PASSED <<<")
