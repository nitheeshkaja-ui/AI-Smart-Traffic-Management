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

print("=== STARTING 30-SECOND SIMULATION TEST ===")
for lane in sim.lanes:
    print(f"Initial {lane.upper()}: count={len(sim.vehicles[lane])}, y_pos={[round(v.y_pos, 1) for v in sim.vehicles[lane]]}")

start_time = time.perf_counter()
last_tick = start_time
steps = 0
last_report = start_time

while time.perf_counter() - start_time < 30.0:
    loop_start = time.perf_counter()
    raw_delta = loop_start - last_tick
    last_tick = loop_start
    dt = max(0.001, min(0.1, raw_delta))

    signal_state = agent.get_signal_states()
    sim.update_physics(signal_state, delta_time=dt)

    raw_frames = {}
    for lane in sim.lanes:
        frame = sim.render_lane_frame(lane, signal_state["signals"][lane])
        dets = detector.detect(frame, is_synthetic=True)
        analyzer.process_lane_detections(lane, dets)

    snapshot = analyzer.get_intersection_snapshot()
    agent.tick(dt, snapshot)

    steps += 1
    if time.perf_counter() - last_report >= 5.0:
        last_report = time.perf_counter()
        elapsed = round(last_report - start_time, 1)
        active = agent.current_lane
        phase = agent.current_phase
        time_rem = agent.phase_time_remaining
        print(f"\n--- t={elapsed}s | Active: {active.upper()} {phase} ({round(time_rem, 1)}s left) ---")
        for lane in sim.lanes:
            vehs = sim.vehicles[lane]
            print(f"  {lane.upper():5s}: count={len(vehs)} | y_pos={[round(v.y_pos, 1) for v in vehs]}")

    # Sleep to pace at 25 fps
    elapsed_frame = time.perf_counter() - loop_start
    time.sleep(max(0.005, (1.0 / 25.0) - elapsed_frame))

print("\n=== FINAL STATE AFTER 30 SECONDS ===")
for lane in sim.lanes:
    vehs = sim.vehicles[lane]
    print(f"Final {lane.upper()}: count={len(vehs)}, y_pos={[round(v.y_pos, 1) for v in vehs]}")
