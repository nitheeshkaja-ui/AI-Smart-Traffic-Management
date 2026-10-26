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

print("Initial:")
for lane in sim.lanes:
    print(lane, [round(v.y_pos, 1) for v in sim.vehicles[lane]])

start_time = time.perf_counter()
last_tick = start_time

for frame_idx in range(50): # 2 seconds at 25 fps
    loop_start = time.perf_counter()
    raw_delta = loop_start - last_tick
    last_tick = loop_start
    dt = max(0.001, min(0.1, raw_delta))

    signal_state = agent.get_signal_states()
    if frame_idx < 10:
        print(f"Frame {frame_idx}: current_lane={agent.current_lane}, phase={agent.current_phase}, north_color={signal_state['signals']['north']['color']}, dt={dt:.4f}")
        print("   north y_pos:", [round(v.y_pos, 2) for v in sim.vehicles['north']])

    sim.update_physics(signal_state, delta_time=dt)

    raw_frames = {}
    for lane in sim.lanes:
        frame = sim.render_lane_frame(lane, signal_state["signals"][lane])
        dets = detector.detect(frame, is_synthetic=True)
        analyzer.process_lane_detections(lane, dets)

    snapshot = analyzer.get_intersection_snapshot()
    agent.tick(dt, snapshot)

    time.sleep(0.04)

print("After 2s:")
for lane in sim.lanes:
    print(lane, [round(v.y_pos, 1) for v in sim.vehicles[lane]])
