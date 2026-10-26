/**
 * AI-Based Smart Traffic Management System
 * GitHub Pages Client & Interactive Dual-Mode Controller
 * Supports:
 *   1. Remote/Local Live Backend Mode (REST API + MJPEG OpenCV Streams)
 *   2. Standalone Interactive Demo Mode (Client-Side Simulation & Canvas Rendering)
 */

const LANES = ['north', 'south', 'east', 'west'];
const LANE_NAMES = {
  north: 'North Approach',
  south: 'South Approach',
  east: 'East Approach',
  west: 'West Approach'
};

// State flags
let isLiveBackend = false;
let backendCheckInProgress = false;
let activeRushHourLanes = new Set();
let pollIntervalTimer = null;
let watchdogRecheckTimer = null;

// Clock ticker
function startClock() {
  const clockEl = document.getElementById('clockDisplay');
  function update() {
    const now = new Date();
    if (clockEl) {
      clockEl.textContent = now.toTimeString().split(' ')[0];
    }
  }
  setInterval(update, 1000);
  update();
}

// Backend URL Resolution
function getBackendUrl() {
  const saved = localStorage.getItem('traffic_backend_url');
  if (saved && saved.trim() !== '') {
    return saved.trim().replace(/\/+$/, '');
  }
  // Local environment defaults to relative root (same origin)
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return '';
  }
  // On GitHub Pages or static host without configured backend
  return '';
}

function setBackendUrl(url) {
  if (!url || url.trim() === '') {
    localStorage.removeItem('traffic_backend_url');
  } else {
    localStorage.setItem('traffic_backend_url', url.trim().replace(/\/+$/, ''));
  }
}

// =========================================================================
// Backend API Communication (Live Mode)
// =========================================================================

async function apiFetch(endpoint, options = {}) {
  const baseUrl = getBackendUrl();
  const url = `${baseUrl}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);
  
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

async function checkBackendHealth() {
  try {
    const res = await apiFetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      if (data && data.status === 'success') {
        return { ok: true, data };
      }
    }
    return { ok: false };
  } catch (err) {
    return { ok: false, error: err };
  }
}

// Update dashboard with snapshot from backend
function updateDashboard(data) {
  if (!data || data.status !== 'success') return;

  const signals = data.signals || {};
  const intersection = data.intersection || {};
  const laneMetrics = intersection.lanes || {};
  const stats = data.stats || {};
  const laneNames = data.lane_names || LANE_NAMES;

  // 1. Update Lane Panels (Signals, Timers, Metrics, Labels, Badges)
  LANES.forEach((lane) => {
    const sig = signals[lane] || { color: 'RED', seconds_left: 0 };
    const metric = laneMetrics[lane] || { total_vehicles: 0, total_pcu: 0, congestion_level: 'Low' };

    // Dynamic lane label
    const labelEl = document.getElementById(`label-${lane}`);
    if (labelEl) labelEl.textContent = laneNames[lane] || lane.toUpperCase();

    // Signal bulbs
    const hud = document.getElementById(`hud-${lane}`);
    if (hud) {
      const redBulb = hud.querySelector('.signal-bulb.red');
      const yellowBulb = hud.querySelector('.signal-bulb.yellow');
      const greenBulb = hud.querySelector('.signal-bulb.green');

      if (redBulb) redBulb.classList.toggle('active', sig.color === 'RED' || sig.color === 'ALL_RED');
      if (yellowBulb) yellowBulb.classList.toggle('active', sig.color === 'YELLOW');
      if (greenBulb) greenBulb.classList.toggle('active', sig.color === 'GREEN');
    }

    // Timer badge
    const timerEl = document.getElementById(`timer-${lane}`);
    if (timerEl) {
      timerEl.textContent = `${sig.seconds_left}s`;
    }

    // Vehicle count & PCU
    const cntEl = document.getElementById(`cnt-${lane}`);
    if (cntEl) cntEl.textContent = metric.total_vehicles;

    const pcuEl = document.getElementById(`pcu-${lane}`);
    if (pcuEl) pcuEl.textContent = Number(metric.total_pcu).toFixed(1);

    // Congestion pill
    const congEl = document.getElementById(`cong-${lane}`);
    if (congEl) {
      congEl.textContent = metric.congestion_level;
      congEl.className = `status-pill ${metric.congestion_level.toLowerCase()}`;
    }

    // Dynamic Density Bar
    const barValEl = document.getElementById(`bar-val-${lane}`);
    const barFillEl = document.getElementById(`bar-fill-${lane}`);
    if (barValEl && barFillEl) {
      barValEl.textContent = `${Number(metric.total_pcu).toFixed(1)} PCU`;
      const fillPct = Math.min(100, (metric.total_pcu / 20.0) * 100);
      barFillEl.style.width = `${fillPct}%`;

      if (metric.congestion_level === 'Critical') {
        barFillEl.style.background = 'linear-gradient(90deg, #ff1744, #ff5252)';
      } else if (metric.congestion_level === 'High') {
        barFillEl.style.background = 'linear-gradient(90deg, #ff9100, #ffab40)';
      } else {
        barFillEl.style.background = 'linear-gradient(90deg, #00f2fe, #4facfe)';
      }
    }
  });

  // 2. Emergency Override Alert Banner
  const emergencyBanner = document.getElementById('emergencyBanner');
  const emergencyText = document.getElementById('emergencyLaneText');
  if (emergencyBanner && emergencyText) {
    if (data.emergency_override_active && data.emergency_lane) {
      emergencyBanner.classList.remove('hidden');
      emergencyText.textContent = `EMERGENCY VEHICLE IN ${data.emergency_lane.toUpperCase()} APPROACH! Priority signal clearance active.`;
    } else {
      emergencyBanner.classList.add('hidden');
    }
  }

  // 3. Overall KPI Panel
  const kpiVehicles = document.getElementById('kpi-vehicles');
  const kpiPcu = document.getElementById('kpi-pcu');
  const kpiSaved = document.getElementById('kpi-saved');
  const kpiEv = document.getElementById('kpi-ev-count');

  if (kpiVehicles) kpiVehicles.textContent = intersection.total_intersection_vehicles || 0;
  if (kpiPcu) kpiPcu.textContent = Number(intersection.total_intersection_pcu || 0).toFixed(1);
  if (kpiSaved) kpiSaved.textContent = `${Math.round(stats.wait_time_saved_sec || 0)}s`;
  if (kpiEv) kpiEv.textContent = stats.emergency_overrides || 0;

  // 4. Update Event Logs
  const logStream = document.getElementById('logStream');
  if (logStream && data.recent_events && data.recent_events.length > 0) {
    logStream.innerHTML = '';
    data.recent_events.forEach((evt) => {
      const entry = document.createElement('div');
      const isAlert = evt.message.includes('Emergency') || evt.message.includes('OVERRIDE');
      entry.className = `log-entry ${isAlert ? 'alert' : ''}`;
      entry.innerHTML = `<span class="log-time">[${evt.timestamp}]</span> ${evt.message}`;
      logStream.appendChild(entry);
    });
    logStream.scrollTop = logStream.scrollHeight;
  }
}

// Periodic polling loop in live mode
async function pollBackendStatus() {
  if (!isLiveBackend) return;
  try {
    const res = await apiFetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      updateDashboard(data);
    } else {
      // Temporary error or backend down
      switchToDemoMode('Backend unreachable');
    }
  } catch (e) {
    switchToDemoMode('Connection lost');
  }
}

// Setup stream watchdogs for video feeds in live mode
function setupLiveStreams() {
  const baseUrl = getBackendUrl();
  LANES.forEach((lane) => {
    const img = document.getElementById(`stream-${lane}`);
    const canvas = document.getElementById(`canvas-${lane}`);

    if (img && canvas) {
      img.classList.remove('hidden');
      canvas.classList.add('hidden');
      img.src = `${baseUrl}/simulation_feed/${lane}?t=${Date.now()}`;

      img.onerror = () => {
        console.warn(`Live stream dropped for ${lane}. Falling back to canvas preview...`);
        img.classList.add('hidden');
        canvas.classList.remove('hidden');
      };
    }
  });
}

// =========================================================================
// Standalone Client-Side Demo Simulation Engine
// =========================================================================

class DemoVehicle {
  constructor(lane, vType, yPos, speed, isEmergency = false) {
    this.lane = lane;
    this.vType = vType;
    this.y = yPos;
    this.speed = speed;
    this.targetSpeed = speed;
    this.isEmergency = isEmergency;
    this.strobe = 0;

    if (vType === 'bus') {
      this.w = 34;
      this.h = 80;
      this.color = '#e69138';
      this.pcu = 2.5;
    } else if (vType === 'truck') {
      this.w = 36;
      this.h = 90;
      this.color = '#3d85c6';
      this.pcu = 3.0;
    } else if (vType === 'motorcycle') {
      this.w = 16;
      this.h = 32;
      this.color = '#ab47bc';
      this.pcu = 0.5;
    } else if (isEmergency) {
      this.w = 32;
      this.h = 70;
      this.color = '#ffffff';
      this.pcu = 3.5;
      this.speed = 3.2;
      this.targetSpeed = 3.2;
    } else {
      // standard car
      this.w = 28;
      this.h = 55;
      const colors = ['#e53935', '#43a047', '#1e88e5', '#fbc02d', '#eceff1'];
      this.color = colors[Math.floor(Math.random() * colors.length)];
      this.pcu = 1.0;
    }
  }
}

class DemoSimulationEngine {
  constructor() {
    this.lanes = ['north', 'south', 'east', 'west'];
    this.vehicles = { north: [], south: [], east: [], west: [] };
    this.signals = {
      north: { color: 'GREEN', seconds_left: 20 },
      south: { color: 'RED', seconds_left: 20 },
      east: { color: 'RED', seconds_left: 20 },
      west: { color: 'RED', seconds_left: 20 }
    };
    this.currentLane = 'north';
    this.currentPhase = 'GREEN';
    this.phaseRemaining = 20;
    this.allocatedGreen = 20;
    this.mode = 'AUTO_ADAPTIVE';
    this.emergencyActive = false;
    this.emergencyLane = null;
    this.stats = { waitSaved: 142, emergenciesCleared: 0 };
    this.events = [
      { timestamp: new Date().toTimeString().split(' ')[0], message: 'Standalone Simulation Engine initialized.' },
      { timestamp: new Date().toTimeString().split(' ')[0], message: 'Adaptive PCU Signal Controller online.' }
    ];
    this.laneWaitingTimes = { north: 0, south: 0, east: 0, west: 0 };

    // Initial vehicle population
    this.lanes.forEach((l) => this.seedLane(l));
  }

  seedLane(lane) {
    const count = 2 + Math.floor(Math.random() * 2);
    let y = 180;
    for (let i = 0; i < count; i++) {
      const types = ['car', 'car', 'bus', 'truck', 'motorcycle'];
      const vt = types[Math.floor(Math.random() * types.length)];
      const v = new DemoVehicle(lane, vt, y, 1.8 + Math.random() * 0.8);
      this.vehicles[lane].push(v);
      y += v.h + 20;
    }
  }

  logEvent(msg) {
    const timeStr = new Date().toTimeString().split(' ')[0];
    this.events.push({ timestamp: timeStr, message: msg });
    if (this.events.length > 25) this.events.shift();
  }

  injectEmergency(lane) {
    if (!this.lanes.includes(lane)) return;
    const ev = new DemoVehicle(lane, 'car', 420, 3.2, true);
    this.vehicles[lane].push(ev);
    this.emergencyActive = true;
    this.emergencyLane = lane;
    this.logEvent(`EMERGENCY: Ambulance detected on ${LANE_NAMES[lane]}! Triggering preemption.`);

    if (this.currentLane !== lane || this.currentPhase !== 'GREEN') {
      if (this.currentPhase === 'GREEN') {
        this.currentPhase = 'YELLOW';
        this.phaseRemaining = 3;
      }
    }
  }

  manualGreen(lane) {
    if (!this.lanes.includes(lane)) return;
    this.mode = 'MANUAL_OVERRIDE';
    document.getElementById('modeSelect').value = 'MANUAL_OVERRIDE';
    this.currentLane = lane;
    this.currentPhase = 'GREEN';
    this.phaseRemaining = 25;
    this.logEvent(`MANUAL: Operator forced Green for ${LANE_NAMES[lane]}.`);
  }

  stepStateMachine() {
    this.phaseRemaining -= 1;

    // Track wait times for starving lanes
    this.lanes.forEach((l) => {
      if (l !== this.currentLane && this.vehicles[l].length > 0) {
        this.laneWaitingTimes[l] += 1;
      } else if (l === this.currentLane && this.currentPhase === 'GREEN') {
        this.laneWaitingTimes[l] = 0;
      }
    });

    if (this.phaseRemaining <= 0) {
      if (this.currentPhase === 'GREEN') {
        this.currentPhase = 'YELLOW';
        this.phaseRemaining = 3;
      } else if (this.currentPhase === 'YELLOW') {
        this.currentPhase = 'ALL_RED';
        this.phaseRemaining = 2;
      } else if (this.currentPhase === 'ALL_RED') {
        // Select next lane
        this.currentLane = this.selectNextLane();
        this.currentPhase = 'GREEN';
        this.allocatedGreen = this.calculateGreenTime(this.currentLane);
        this.phaseRemaining = this.allocatedGreen;
        this.logEvent(`PHASE: Green granted to ${LANE_NAMES[this.currentLane]} for ${this.allocatedGreen}s.`);
      }
    }

    // Check emergency clearance
    if (this.emergencyActive && this.emergencyLane) {
      const evs = this.vehicles[this.emergencyLane].filter((v) => v.isEmergency && v.y > 150);
      if (evs.length === 0) {
        this.emergencyActive = false;
        this.stats.emergenciesCleared += 1;
        this.logEvent(`EMERGENCY: Ambulance in ${LANE_NAMES[this.emergencyLane]} cleared intersection.`);
        this.emergencyLane = null;
      }
    }

    // Update signal states dictionary
    this.lanes.forEach((lane) => {
      if (lane === this.currentLane) {
        this.signals[lane] = { color: this.currentPhase, seconds_left: Math.max(0, this.phaseRemaining) };
      } else {
        this.signals[lane] = { color: 'RED', seconds_left: Math.max(0, this.phaseRemaining) };
      }
    });
  }

  selectNextLane() {
    // 1. Emergency Preemption
    if (this.emergencyActive && this.emergencyLane) {
      return this.emergencyLane;
    }

    // 2. Anti-Starvation Check (lane waiting >= 90s)
    let starvingLane = null;
    let maxWait = -1;
    this.lanes.forEach((l) => {
      if (l !== this.currentLane && this.laneWaitingTimes[l] >= 90) {
        if (this.laneWaitingTimes[l] > maxWait) {
          maxWait = this.laneWaitingTimes[l];
          starvingLane = l;
        }
      }
    });
    if (starvingLane) {
      this.logEvent(`ANTI-STARVATION: ${LANE_NAMES[starvingLane]} reached ${maxWait}s wait! Forced green.`);
      return starvingLane;
    }

    // 3. Mode Decision
    if (this.mode === 'FIXED_TIME') {
      const idx = (this.lanes.indexOf(this.currentLane) + 1) % this.lanes.length;
      return this.lanes[idx];
    }

    // 4. Adaptive AI: Max PCU
    let highestPcu = -1;
    let bestLane = this.lanes[0];
    this.lanes.forEach((l) => {
      if (l !== this.currentLane) {
        const pcu = this.computeLanePcu(l);
        if (pcu > highestPcu) {
          highestPcu = pcu;
          bestLane = l;
        }
      }
    });
    return bestLane;
  }

  computeLanePcu(lane) {
    return this.vehicles[lane].reduce((acc, v) => acc + v.pcu, 0);
  }

  calculateGreenTime(lane) {
    if (this.mode === 'FIXED_TIME') return 20;
    const lanePcu = this.computeLanePcu(lane);
    const totalPcu = this.lanes.reduce((acc, l) => acc + this.computeLanePcu(l), 0);
    if (totalPcu <= 0) return 10;
    const ratio = Math.min(1.0, lanePcu / Math.max(1.0, totalPcu));
    const dynamicTime = Math.round(10 + ratio * 40);
    return Math.max(10, Math.min(50, dynamicTime));
  }

  updatePhysics(dt) {
    this.lanes.forEach((lane) => {
      const isGreen = lane === this.currentLane && this.currentPhase === 'GREEN';
      const isYellow = lane === this.currentLane && this.currentPhase === 'YELLOW';
      const stopLine = 150.0;
      const vehList = this.vehicles[lane];

      // Sort by y ascending (closest to intersection first)
      vehList.sort((a, b) => a.y - b.y);

      vehList.forEach((v, i) => {
        let maxAllowedSpeed = v.targetSpeed;
        const distToStop = v.y - stopLine;

        if (!isGreen) {
          if (distToStop > 0 && distToStop < 90) {
            maxAllowedSpeed = Math.max(0, (distToStop / 90.0) * v.targetSpeed);
            if (distToStop < 6) maxAllowedSpeed = 0;
          }
        }

        // Car following
        if (i > 0) {
          const lead = vehList[i - 1];
          const gap = v.y - (lead.y + lead.h);
          if (gap < 24) {
            maxAllowedSpeed = Math.min(maxAllowedSpeed, lead.speed * 0.85);
            if (gap < 8) maxAllowedSpeed = 0;
          }
        }

        // Accelerate or brake
        if (v.speed < maxAllowedSpeed) {
          v.speed = Math.min(maxAllowedSpeed, v.speed + 0.12);
        } else if (v.speed > maxAllowedSpeed) {
          v.speed = Math.max(maxAllowedSpeed, v.speed - 0.25);
        }

        // Move vehicle towards stop line / through intersection
        v.y -= v.speed * (dt * 26);
        v.strobe = (v.strobe + 1) % 10;
      });

      // Filter out vehicles that crossed intersection
      this.vehicles[lane] = vehList.filter((v) => v.y > -80);

      // Random vehicle spawn
      const isRush = activeRushHourLanes.has(lane);
      const spawnChance = isRush ? 0.04 : 0.015;
      const maxY = vehList.length > 0 ? Math.max(...vehList.map((v) => v.y)) : 160;

      if (Math.random() < spawnChance && maxY < 400 && vehList.length < 7) {
        const types = ['car', 'car', 'bus', 'truck', 'motorcycle'];
        const vt = types[Math.floor(Math.random() * types.length)];
        const newV = new DemoVehicle(lane, vt, 460, 1.8 + Math.random() * 0.8);
        this.vehicles[lane].push(newV);
      }
    });
  }

  renderCanvas(lane) {
    const canvas = document.getElementById(`canvas-${lane}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    // 1. Background Road
    ctx.fillStyle = '#161b24';
    ctx.fillRect(0, 0, w, h);

    // Roadway asphalt
    const roadWidth = 260;
    const roadX = (w - roadWidth) / 2;
    ctx.fillStyle = '#222834';
    ctx.fillRect(roadX, 0, roadWidth, h);

    // Curb lines
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(roadX, 0);
    ctx.lineTo(roadX, h);
    ctx.moveTo(roadX + roadWidth, 0);
    ctx.lineTo(roadX + roadWidth, h);
    ctx.stroke();

    // Center dashed line
    ctx.strokeStyle = '#f6e05e';
    ctx.lineWidth = 3;
    ctx.setLineDash([20, 15]);
    ctx.beginPath();
    ctx.moveTo(w / 2, 0);
    ctx.lineTo(w / 2, h);
    ctx.stroke();
    ctx.setLineDash([]);

    // Stop Line (y = 150)
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(roadX, 146, roadWidth, 8);

    // Zebra Crossing behind stop line
    ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
    for (let zx = roadX + 10; zx < roadX + roadWidth - 10; zx += 24) {
      ctx.fillRect(zx, 95, 14, 45);
    }

    // Direction arrow
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.beginPath();
    ctx.moveTo(w / 2, 175);
    ctx.lineTo(w / 2 - 12, 195);
    ctx.lineTo(w / 2 - 5, 195);
    ctx.lineTo(w / 2 - 5, 220);
    ctx.lineTo(w / 2 + 5, 220);
    ctx.lineTo(w / 2 + 5, 195);
    ctx.lineTo(w / 2 + 12, 195);
    ctx.closePath();
    ctx.fill();

    // 2. Render Vehicles
    const vehList = this.vehicles[lane];
    vehList.forEach((v) => {
      const vx = (w - v.w) / 2;
      const vy = v.y;

      ctx.save();
      // Vehicle shadow
      ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
      ctx.fillRect(vx + 4, vy + 4, v.w, v.h);

      // Vehicle body
      ctx.fillStyle = v.color;
      ctx.fillRect(vx, vy, v.w, v.h);
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(vx, vy, v.w, v.h);

      // Windshield & Roof
      ctx.fillStyle = '#1a202c';
      ctx.fillRect(vx + 3, vy + 10, v.w - 6, Math.max(6, v.h * 0.18));
      ctx.fillRect(vx + 3, vy + v.h - 14, v.w - 6, Math.max(4, v.h * 0.12));

      // Headlights
      ctx.fillStyle = '#fff59d';
      ctx.fillRect(vx + 2, vy, 4, 3);
      ctx.fillRect(vx + v.w - 6, vy, 4, 3);

      // Taillights
      ctx.fillStyle = v.speed === 0 ? '#ff1744' : '#b71c1c';
      ctx.fillRect(vx + 2, vy + v.h - 3, 4, 3);
      ctx.fillRect(vx + v.w - 6, vy + v.h - 3, 4, 3);

      // Emergency Vehicle Markings & Strobe Lights
      if (v.isEmergency) {
        // Red cross on roof
        ctx.fillStyle = '#d50000';
        ctx.fillRect(vx + v.w / 2 - 2, vy + v.h / 2 - 8, 4, 16);
        ctx.fillRect(vx + v.w / 2 - 8, vy + v.h / 2 - 2, 16, 4);

        // Flashing strobes
        const isRedStrobe = v.strobe < 5;
        ctx.fillStyle = isRedStrobe ? '#ff1744' : '#00b0ff';
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.arc(vx + 6, vy + 8, 4, 0, Math.PI * 2);
        ctx.arc(vx + v.w - 6, vy + 8, 4, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    });

    // 3. Traffic Light Indicator Graphic in corner
    const sig = this.signals[lane];
    ctx.save();
    ctx.fillStyle = '#0a0d14';
    ctx.strokeStyle = '#2d3748';
    ctx.lineWidth = 2;
    ctx.fillRect(w - 55, 15, 40, 85);
    ctx.strokeRect(w - 55, 15, 40, 85);

    // Bulbs
    const bulbs = [
      { y: 30, color: '#ff3b30', active: sig.color === 'RED' || sig.color === 'ALL_RED' },
      { y: 55, color: '#ffcc00', active: sig.color === 'YELLOW' },
      { y: 80, color: '#34c759', active: sig.color === 'GREEN' }
    ];

    bulbs.forEach((b) => {
      ctx.beginPath();
      ctx.arc(w - 35, b.y, 8, 0, Math.PI * 2);
      if (b.active) {
        ctx.fillStyle = b.color;
        ctx.shadowColor = b.color;
        ctx.shadowBlur = 12;
      } else {
        ctx.fillStyle = '#222834';
        ctx.shadowBlur = 0;
      }
      ctx.fill();
    });
    ctx.restore();
  }

  getSnapshot() {
    let totalIntersectionVehicles = 0;
    let totalIntersectionPcu = 0;
    const laneMetrics = {};

    this.lanes.forEach((l) => {
      const vCount = this.vehicles[l].length;
      const pcu = this.computeLanePcu(l);
      totalIntersectionVehicles += vCount;
      totalIntersectionPcu += pcu;

      let cong = 'Low';
      if (pcu >= 18) cong = 'Critical';
      else if (pcu >= 12) cong = 'High';
      else if (pcu >= 6) cong = 'Moderate';

      laneMetrics[l] = {
        total_vehicles: vCount,
        total_pcu: pcu,
        congestion_level: cong
      };
    });

    return {
      status: 'success',
      signals: this.signals,
      active_lane: this.currentLane,
      active_phase: this.currentPhase,
      phase_time_remaining: this.phaseRemaining,
      phase_allocated_time: this.allocatedGreen,
      emergency_override_active: this.emergencyActive,
      emergency_lane: this.emergencyLane,
      mode: this.mode,
      lane_names: LANE_NAMES,
      stats: {
        wait_time_saved_sec: this.stats.waitSaved,
        emergency_overrides: this.stats.emergenciesCleared
      },
      recent_events: this.events,
      intersection: {
        total_intersection_vehicles: totalIntersectionVehicles,
        total_intersection_pcu: totalIntersectionPcu,
        lanes: laneMetrics
      }
    };
  }
}

const demoEngine = new DemoSimulationEngine();

// =========================================================================
// Mode Transitions & Master Control
// =========================================================================

function switchToLiveMode(initialData) {
  isLiveBackend = true;
  const statusBadge = document.getElementById('statusBadge');
  const statusText = document.getElementById('systemStatusText');

  if (statusBadge && statusText) {
    statusBadge.className = 'system-status-badge';
    statusText.textContent = 'LIVE BACKEND (CONNECTED)';
  }

  setupLiveStreams();
  updateDashboard(initialData);

  if (pollIntervalTimer) clearInterval(pollIntervalTimer);
  pollIntervalTimer = setInterval(pollBackendStatus, 1000);
}

function switchToDemoMode(reason = '') {
  isLiveBackend = false;
  const statusBadge = document.getElementById('statusBadge');
  const statusText = document.getElementById('systemStatusText');

  if (statusBadge && statusText) {
    statusBadge.className = 'system-status-badge demo';
    statusText.textContent = 'DEMO SIMULATION (CLIENT-SIDE)';
  }

  // Switch views to canvas
  LANES.forEach((lane) => {
    const img = document.getElementById(`stream-${lane}`);
    const canvas = document.getElementById(`canvas-${lane}`);
    if (img && canvas) {
      img.classList.add('hidden');
      canvas.classList.remove('hidden');
    }
  });

  if (pollIntervalTimer) clearInterval(pollIntervalTimer);

  // Re-verify backend occasionally if user entered a URL
  if (watchdogRecheckTimer) clearTimeout(watchdogRecheckTimer);
  const backendUrl = getBackendUrl();
  if (backendUrl) {
    watchdogRecheckTimer = setTimeout(async () => {
      const res = await checkBackendHealth();
      if (res.ok) {
        switchToLiveMode(res.data);
      }
    }, 10000);
  }
}

// User Action Handlers (Dual-Mode aware)
async function injectEmergency(lane) {
  if (isLiveBackend) {
    try {
      await apiFetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'inject_emergency', lane: lane })
      });
      return;
    } catch (e) {
      console.warn('Backend control failed. Applying to demo engine.');
    }
  }
  demoEngine.injectEmergency(lane);
  updateDashboard(demoEngine.getSnapshot());
}

async function toggleRushHour(lane) {
  const isRush = activeRushHourLanes.has(lane);
  const newLevel = isRush ? 'normal' : 'rush_hour';

  if (isRush) {
    activeRushHourLanes.delete(lane);
  } else {
    activeRushHourLanes.add(lane);
  }

  if (isLiveBackend) {
    try {
      await apiFetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'set_traffic_level', lane: lane, level: newLevel })
      });
      return;
    } catch (e) {
      console.warn('Backend control failed.');
    }
  }

  demoEngine.logEvent(`TRAFFIC: Rush hour ${newLevel === 'rush_hour' ? 'activated' : 'deactivated'} for ${LANE_NAMES[lane]}.`);
}

async function manualGreen(lane) {
  if (isLiveBackend) {
    try {
      const modeSelect = document.getElementById('modeSelect');
      if (modeSelect) modeSelect.value = 'MANUAL_OVERRIDE';
      await apiFetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'manual_green', lane: lane })
      });
      return;
    } catch (e) {
      console.warn('Backend control failed. Applying to demo engine.');
    }
  }
  demoEngine.manualGreen(lane);
  updateDashboard(demoEngine.getSnapshot());
}

// Control Mode Selector Handler
const modeSelect = document.getElementById('modeSelect');
if (modeSelect) {
  modeSelect.addEventListener('change', async (e) => {
    const mode = e.target.value;
    if (isLiveBackend) {
      try {
        await apiFetch('/api/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'set_mode', mode: mode })
        });
        return;
      } catch (err) {
        console.warn('Failed to post mode to backend:', err);
      }
    }
    demoEngine.mode = mode;
    demoEngine.logEvent(`MODE: Control mode changed to ${mode}.`);
  });
}

// =========================================================================
// Backend Config Modal Management
// =========================================================================

function setupBackendConfigModal() {
  const modal = document.getElementById('backendModal');
  const btnToggle = document.getElementById('btnBackendToggle');
  const btnClose = document.getElementById('btnCloseModal');
  const inputUrl = document.getElementById('inputBackendUrl');
  const btnSave = document.getElementById('btnSaveBackendUrl');
  const btnTest = document.getElementById('btnTestConnection');
  const btnDemo = document.getElementById('btnUseDemoMode');
  const statusBox = document.getElementById('modalStatusBox');

  if (!modal || !btnToggle) return;

  btnToggle.addEventListener('click', () => {
    inputUrl.value = getBackendUrl();
    statusBox.className = 'status-box';
    statusBox.textContent = isLiveBackend
      ? `Connected to: ${getBackendUrl() || 'Local Flask (same-origin)'}`
      : 'Currently running in Standalone Demo Mode.';
    modal.classList.remove('hidden');
  });

  const closeModal = () => modal.classList.add('hidden');
  if (btnClose) btnClose.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  if (btnTest) {
    btnTest.addEventListener('click', async () => {
      const url = inputUrl.value.trim().replace(/\/+$/, '');
      statusBox.className = 'status-box';
      statusBox.textContent = 'Testing connection...';

      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 4000);
        const res = await fetch(`${url}/api/status`, { signal: controller.signal });
        clearTimeout(timeout);
        if (res.ok) {
          statusBox.className = 'status-box success';
          statusBox.textContent = 'Connection successful! Live backend is reachable.';
        } else {
          statusBox.className = 'status-box error';
          statusBox.textContent = `Server responded with HTTP status ${res.status}.`;
        }
      } catch (err) {
        statusBox.className = 'status-box error';
        statusBox.textContent = `Connection failed: ${err.message}. Ensure backend is running and CORS is enabled.`;
      }
    });
  }

  if (btnSave) {
    btnSave.addEventListener('click', async () => {
      const url = inputUrl.value.trim().replace(/\/+$/, '');
      setBackendUrl(url);
      closeModal();

      const health = await checkBackendHealth();
      if (health.ok) {
        switchToLiveMode(health.data);
      } else {
        switchToDemoMode('Backend unreachable at specified URL');
      }
    });
  }

  if (btnDemo) {
    btnDemo.addEventListener('click', () => {
      setBackendUrl('');
      closeModal();
      switchToDemoMode('User selected demo mode');
    });
  }
}

// =========================================================================
// Main Loop & Initialization
// =========================================================================

let lastPhysicsTime = performance.now();

function animationLoop(timestamp) {
  const dt = Math.max(0.005, Math.min(0.1, (timestamp - lastPhysicsTime) / 1000.0));
  lastPhysicsTime = timestamp;

  if (!isLiveBackend) {
    demoEngine.updatePhysics(dt);
    LANES.forEach((lane) => demoEngine.renderCanvas(lane));
  }

  requestAnimationFrame(animationLoop);
}

// Initialize application on load
window.addEventListener('DOMContentLoaded', async () => {
  startClock();
  setupBackendConfigModal();

  // Start continuous canvas rendering loop
  requestAnimationFrame(animationLoop);

  // Start demo state machine ticker (1-second tick)
  setInterval(() => {
    if (!isLiveBackend) {
      demoEngine.stepStateMachine();
      updateDashboard(demoEngine.getSnapshot());
    }
  }, 1000);

  // Initial backend health check
  const health = await checkBackendHealth();
  if (health.ok) {
    switchToLiveMode(health.data);
  } else {
    switchToDemoMode('Defaulting to standalone interactive demo');
    updateDashboard(demoEngine.getSnapshot());
  }
});
