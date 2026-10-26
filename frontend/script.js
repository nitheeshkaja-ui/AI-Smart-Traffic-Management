/**
 * AI-Based Smart Traffic Management System
 * Frontend Controller & Real-Time Simulation Dashboard Client
 */

const LANES = ['north', 'south', 'east', 'west'];
let activeRushHourLanes = new Set();

// Clock ticker
function startClock() {
  const clockEl = document.getElementById('clockDisplay');
  function update() {
    const now = new Date();
    clockEl.textContent = now.toTimeString().split(' ')[0];
  }
  setInterval(update, 1000);
  update();
}

// Control Mode Change
document.getElementById('modeSelect').addEventListener('change', async (e) => {
  const mode = e.target.value;
  try {
    await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_mode', mode: mode })
    });
  } catch (err) {
    console.error('Failed to change mode:', err);
  }
});

// Inject Emergency Vehicle (Ambulance)
async function injectEmergency(lane) {
  try {
    await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'inject_emergency', lane: lane })
    });
  } catch (err) {
    console.error('Failed to inject emergency vehicle:', err);
  }
}

// Toggle Rush Hour Congestion Level
async function toggleRushHour(lane) {
  const isRush = activeRushHourLanes.has(lane);
  const newLevel = isRush ? 'normal' : 'rush_hour';

  if (isRush) {
    activeRushHourLanes.delete(lane);
  } else {
    activeRushHourLanes.add(lane);
  }

  try {
    await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_traffic_level', lane: lane, level: newLevel })
    });
  } catch (err) {
    console.error('Failed to toggle traffic level:', err);
  }
}

// Manual Force Green
async function manualGreen(lane) {
  try {
    document.getElementById('modeSelect').value = 'MANUAL_OVERRIDE';
    await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'manual_green', lane: lane })
    });
  } catch (err) {
    console.error('Failed to trigger manual green:', err);
  }
}

// Update UI with real-time simulation snapshot
function updateDashboard(data) {
  if (!data || data.status !== 'success') return;

  const signals = data.signals || {};
  const intersection = data.intersection || {};
  const laneMetrics = intersection.lanes || {};
  const stats = data.stats || {};
  const laneNames = data.lane_names || {
    north: 'North Approach',
    south: 'South Approach',
    east: 'East Approach',
    west: 'West Approach'
  };

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

      redBulb.classList.toggle('active', sig.color === 'RED' || sig.color === 'ALL_RED');
      yellowBulb.classList.toggle('active', sig.color === 'YELLOW');
      greenBulb.classList.toggle('active', sig.color === 'GREEN');
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
  if (data.emergency_override_active && data.emergency_lane) {
    emergencyBanner.classList.remove('hidden');
    emergencyText.textContent = `EMERGENCY VEHICLE IN ${data.emergency_lane.toUpperCase()} APPROACH! Priority signal clearance active.`;
  } else {
    emergencyBanner.classList.add('hidden');
  }

  // 3. Overall KPI Panel
  document.getElementById('kpi-vehicles').textContent = intersection.total_intersection_vehicles || 0;
  document.getElementById('kpi-pcu').textContent = Number(intersection.total_intersection_pcu || 0).toFixed(1);
  document.getElementById('kpi-saved').textContent = `${Math.round(stats.wait_time_saved_sec || 0)}s`;
  document.getElementById('kpi-ev-count').textContent = stats.emergency_overrides || 0;

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

// Periodic polling loop (1.0s interval)
async function pollStatus() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      updateDashboard(data);
    }
  } catch (e) {
    // Backend briefly busy
  }
}

// Stream watchdog: automatically reconnects if browser drops connection
function setupStreamWatchdogs() {
  LANES.forEach((lane) => {
    const card = document.getElementById(`card-${lane}`);
    if (!card) return;
    const img = card.querySelector('.video-stream');
    if (!img) return;

    img.addEventListener('error', () => {
      console.warn(`Stream dropped for ${lane}. Reconnecting in 1.5s...`);
      setTimeout(() => {
        img.src = `/simulation_feed/${lane}?t=${Date.now()}`;
      }, 1500);
    });
  });
}

// Initialization
window.addEventListener('DOMContentLoaded', () => {
  startClock();
  setupStreamWatchdogs();
  setInterval(pollStatus, 1000);
  pollStatus();
});
