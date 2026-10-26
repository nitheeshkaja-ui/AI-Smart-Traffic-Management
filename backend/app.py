"""
AI-Based Smart Traffic Management System
Module: Simulation Web Application & Real-Time Traffic Stream Server
"""

import os
import sys
import time
import threading
import logging
import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.detection import VehicleDetector
from backend.traffic_analysis import IntersectionTrafficAnalyzer
from backend.decision_agent import TrafficDecisionAgent
from simulation.traffic_simulator import MultiLaneTrafficSimulator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("traffic_server")

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
VALID_LANES = ["north", "south", "east", "west"]
LANE_DISPLAY_NAMES = {
    "north": "North Approach",
    "south": "South Approach",
    "east": "East Approach",
    "west": "West Approach"
}

# Frame & Simulation Parameters
SIMULATION_FPS = 25.0
SIM_FRAME_WIDTH = 640
SIM_FRAME_HEIGHT = 480
JPEG_QUALITY = 75

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Core Engine Components (Pure Simulation Mode: Fast OpenCV Contour Detection, No YOLO/PyTorch)
detector = VehicleDetector(backend="contour")
analyzer = IntersectionTrafficAnalyzer()
decision_agent = TrafficDecisionAgent(yellow_duration=3, all_red_duration=2)
simulator = MultiLaneTrafficSimulator()

# Shared state buffer
is_running = True
frame_buffer_lock = threading.Lock()
lock = frame_buffer_lock  # Backward compatibility alias

latest_annotated_frames = {lane: None for lane in VALID_LANES}
latest_jpeg_buffers = {lane: None for lane in VALID_LANES}
frame_sequence_ids = {lane: 0 for lane in VALID_LANES}
current_annotated_frames = latest_annotated_frames  # Backward compatibility alias
current_frames = latest_annotated_frames  # Backward compatibility alias
lane_sources = {lane: "simulator" for lane in VALID_LANES}


def simulation_traffic_pipeline():
    """
    Continuous background loop for 4-way intersection simulation (~25 FPS):
    1. Updates multi-lane simulator physics using elapsed real time (delta_time).
    2. Renders road frames for North, South, East, and West lanes.
    3. Runs OpenCV vehicle detection and calculates PCU density.
    4. Steps adaptive decision agent state machine (Green -> Yellow 3s -> All-Red 2s -> Green).
    5. Overlays signal bulbs, countdown timers, bounding boxes, and PCU HUD.
    6. Pre-encodes each lane frame to JPEG once and stores in thread memory.
    """
    logger.info("Simulation traffic management pipeline started (Pure Simulation Mode).")
    last_tick = time.perf_counter()
    frame_interval = 1.0 / SIMULATION_FPS

    while is_running:
        loop_start = time.perf_counter()
        raw_delta = loop_start - last_tick
        last_tick = loop_start
        # Clamp delta_time between 5ms and 100ms to guarantee smooth physics and avoid freezing
        clamped_dt = max(0.005, min(0.1, raw_delta))

        # 1. Update simulation physics using real-world elapsed time
        signal_state = decision_agent.get_signal_states()
        simulator.update_physics(signal_state, delta_time=clamped_dt)

        # 2. Render road frames and run OpenCV detection for each direction
        raw_frames = {}
        lane_dets = {}

        for lane in VALID_LANES:
            # Render synthetic road frame
            frame = simulator.render_lane_frame(lane, signal_state["signals"][lane])
            raw_frames[lane] = frame

            # Fast OpenCV contour detection on synthetic geometric roads (~1ms)
            dets = detector.detect(frame, is_synthetic=True)
            lane_dets[lane] = dets
            analyzer.process_lane_detections(lane, dets)

        # 3. Advance decision agent clock
        intersection_snapshot = analyzer.get_intersection_snapshot()
        decision_agent.tick(clamped_dt, intersection_snapshot)

        # 4. Render computer vision overlays and HUD annotations
        updated_signals = decision_agent.get_signal_states()
        new_annotated = {}
        new_jpegs = {}

        for lane, frame in raw_frames.items():
            dets = lane_dets.get(lane, [])
            lane_summary = intersection_snapshot["lanes"].get(lane, {})
            sig_info = updated_signals["signals"].get(lane, {})
            lane_name = LANE_DISPLAY_NAMES.get(lane, lane.upper())

            hud_title = f"{lane_name.upper()} | {sig_info.get('color', 'RED')} ({sig_info.get('seconds_left', 0)}s) | PCU: {lane_summary.get('total_pcu', 0.0):.1f} | OpenCV Contour"
            ann_frame = detector.draw_annotations(frame, dets, header_text=hud_title)
            new_annotated[lane] = ann_frame

            # Pre-encode to JPEG once per frame
            ret, buffer = cv2.imencode(".jpg", ann_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ret:
                new_jpegs[lane] = buffer.tobytes()

        # 5. Atomically update shared annotated frames, JPEG buffers, and sequence IDs
        with frame_buffer_lock:
            for lane in VALID_LANES:
                if lane in new_annotated:
                    latest_annotated_frames[lane] = new_annotated[lane]
                if lane in new_jpegs:
                    latest_jpeg_buffers[lane] = new_jpegs[lane]
                    frame_sequence_ids[lane] += 1

        # Maintain smooth ~25 FPS pacing
        elapsed = time.perf_counter() - loop_start
        sleep_time = max(0.005, frame_interval - elapsed)
        time.sleep(sleep_time)


# Thread startup guard: strictly prevents duplicate worker threads
_workers_started = False
_workers_lock = threading.Lock()

def start_background_workers():
    """Starts background simulation worker thread exactly once."""
    global _workers_started
    with _workers_lock:
        if not _workers_started:
            t_pipeline = threading.Thread(target=simulation_traffic_pipeline, daemon=True, name="SimTrafficPipeline")
            t_pipeline.start()
            _workers_started = True
            logger.info("Simulation pipeline background thread initialized.")

start_background_workers()


# --- HTTP Routes & REST APIs ---

@app.route("/")
def index():
    """Serves the frontend single-page dashboard."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    """Serves styles, scripts, and static resources."""
    return send_from_directory(FRONTEND_DIR, filename)


def generate_mjpeg_stream(lane_id: str):
    """
    Generates continuous MJPEG multipart stream for a given simulation lane.
    Yields pre-encoded JPEG frames only when a fresh frame is ready.
    Zero per-client JPEG encoding overhead. Handles client disconnects cleanly.
    """
    last_seq = -1
    try:
        while is_running:
            frame_bytes = None
            with frame_buffer_lock:
                current_seq = frame_sequence_ids.get(lane_id, 0)
                if current_seq != last_seq:
                    buf = latest_jpeg_buffers.get(lane_id)
                    if buf is not None:
                        frame_bytes = buf
                        last_seq = current_seq

            if frame_bytes is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(0.02)
            else:
                time.sleep(0.015)
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        pass


@app.route("/simulation_feed/<lane_id>")
@app.route("/video_feed/<lane_id>")
def simulation_feed(lane_id: str):
    """MJPEG stream endpoint for a specific simulation lane."""
    if lane_id not in VALID_LANES:
        return "Invalid lane ID", 400
    return Response(generate_mjpeg_stream(lane_id), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status", methods=["GET"])
def get_status():
    """Returns complete real-time status: signals, traffic metrics, and AI decisions."""
    intersection_snapshot = analyzer.get_intersection_snapshot()
    signal_states = decision_agent.get_signal_states()

    with frame_buffer_lock:
        seq_copy = frame_sequence_ids.copy()

    return jsonify({
        "status": "success",
        "signals": signal_states["signals"],
        "active_lane": signal_states["current_lane"],
        "active_phase": signal_states["current_phase"],
        "phase_time_remaining": signal_states["phase_time_remaining"],
        "phase_allocated_time": signal_states["phase_allocated_time"],
        "emergency_override_active": signal_states["emergency_override_active"],
        "emergency_lane": signal_states["emergency_lane"],
        "mode": signal_states["mode"],
        "feed_mode": "simulator",
        "lane_names": LANE_DISPLAY_NAMES,
        "detector_type": "OpenCV Contour",
        "stats": signal_states["stats"],
        "recent_events": signal_states["recent_events"],
        "intersection": intersection_snapshot,
        "lane_sources": {lane: "simulator" for lane in VALID_LANES},
        "frame_sequence_ids": seq_copy
    })


@app.route("/api/control", methods=["POST"])
def post_control():
    """Processes control actions from user dashboard."""
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")

    if action == "set_mode":
        mode = data.get("mode")
        decision_agent.set_mode(mode)
        return jsonify({"status": "success", "message": f"Mode set to {mode}"})

    elif action == "manual_green":
        lane = data.get("lane")
        if lane not in VALID_LANES:
            return jsonify({"status": "error", "message": "Invalid lane"}), 400
        decision_agent.manual_override(lane)
        return jsonify({"status": "success", "message": f"Manual green forced for {lane}"})

    elif action == "inject_emergency":
        lane = data.get("lane", "north")
        if lane not in VALID_LANES:
            return jsonify({"status": "error", "message": "Invalid lane"}), 400
        simulator.inject_emergency_vehicle(lane)
        return jsonify({"status": "success", "message": f"Emergency vehicle injected into {lane}"})

    elif action == "set_traffic_level":
        lane = data.get("lane", "north")
        level = data.get("level", "normal")
        if lane not in VALID_LANES:
            return jsonify({"status": "error", "message": "Invalid lane"}), 400
        simulator.set_traffic_level(lane, level)
        return jsonify({"status": "success", "message": f"Traffic level for {lane} set to {level}"})

    return jsonify({"status": "error", "message": "Unknown action"}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Starting Smart Traffic Management System (Simulation Mode) on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
