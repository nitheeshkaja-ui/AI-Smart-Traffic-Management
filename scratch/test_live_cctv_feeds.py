import time
import requests
import psutil
import os

BASE_URL = "http://127.0.0.1:5050"

print("=== 1. VERIFY INITIAL STATUS (DEFAULT SIMULATOR) ===")
res = requests.get(f"{BASE_URL}/api/status")
data = res.json()
print("Status response:", data["status"])
print("Active feed mode:", data.get("feed_mode"))
print("Camera display names:", data.get("camera_names"))
print("Lane sources:", data.get("lane_sources"))
assert data.get("feed_mode") == "simulator"

print("\n=== 2. TOGGLE TO CCTV MODE (Run_1290) ===")
toggle_res = requests.post(f"{BASE_URL}/api/set_feed_mode", json={"mode": "cctv"})
print("Toggle status:", toggle_res.status_code, toggle_res.json())
assert toggle_res.status_code == 200
assert toggle_res.json()["feed_mode"] == "cctv"

# Let CCTV feeds stream and YOLO infer for a few seconds
print("\n=== 3. MONITORING LIVE CCTV STREAMS & INFERENCE FOR 6 SECONDS ===")
process = psutil.Process(os.getpid())
server_process = None
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    cmd = p.info.get('cmdline') or []
    if any('backend/app.py' in str(c) for c in cmd):
        server_process = p
        break

start_time = time.time()
samples = []
while time.time() - start_time < 6.0:
    st_res = requests.get(f"{BASE_URL}/api/status")
    st = st_res.json()
    total_vehs = st["intersection"]["total_intersection_vehicles"]
    total_pcu = st["intersection"]["total_intersection_pcu"]
    active_phase = f"{st['active_lane']}:{st['active_phase']}"
    samples.append((total_vehs, total_pcu, active_phase))
    time.sleep(1.0)

print("Sampled snapshots during CCTV playback:")
for i, s in enumerate(samples, 1):
    print(f"  Second {i}: Total Vehicles = {s[0]}, Total PCU = {s[1]}, Active Signal = {s[2]}")

if server_process and server_process.is_running():
    cpu_pct = server_process.cpu_percent(interval=1.0)
    mem_info = server_process.memory_info()
    mem_mb = mem_info.rss / (1024 * 1024)
    print(f"\nServer Process Resource Usage:")
    print(f"  CPU Utilization: {cpu_pct:.1f}%")
    print(f"  RAM Memory Usage: {mem_mb:.1f} MB (out of system 8 GB)")

print("\n=== 4. VERIFY VIDEO STREAM RESPONSE FOR ALL 4 CAMERAS ===")
for lane in ["north", "south", "east", "west"]:
    feed_url = f"{BASE_URL}/video_feed/{lane}"
    resp = requests.get(feed_url, stream=True, timeout=5)
    # Read first 10KB to ensure MJPEG multipart stream is transmitting
    chunk = next(resp.iter_content(chunk_size=10240))
    print(f"  Camera stream {lane.upper()}: HTTP {resp.status_code}, read {len(chunk)} bytes from live MJPEG feed")
    assert resp.status_code == 200
    assert len(chunk) > 1000

print("\n=== 5. TOGGLE BACK TO SIMULATOR MODE ===")
revert_res = requests.post(f"{BASE_URL}/api/set_feed_mode", json={"mode": "simulator"})
print("Revert status:", revert_res.status_code, revert_res.json())
assert revert_res.status_code == 200
assert revert_res.json()["feed_mode"] == "simulator"

st_final = requests.get(f"{BASE_URL}/api/status").json()
print("Final lane sources:", st_final.get("lane_sources"))
assert all(src == "simulator" for src in st_final.get("lane_sources", {}).values())

print("\n=== ALL LIVE TESTS AND CHECKS PASSED SUCCESSFULLY ===")
