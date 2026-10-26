# AI-Based Smart Traffic Management System Using Computer Vision

> **College AI Mini-Capstone Project**  
> An end-to-end intelligent traffic control and monitoring system powered by Computer Vision, real-time vehicle density analysis (PCU), dynamic adaptive signal timing, and emergency vehicle priority override (EVPO).

---

## 📌 Executive Summary

Traditional traffic lights operate on rigid, pre-programmed fixed-time schedules. This leads to severe road congestion, unnecessary wait times on empty approaches, increased fuel consumption, higher emissions, and dangerous delays for emergency responders (ambulances and fire engines).

This project implements an **AI-Based Smart Traffic Management System** that uses real-time computer vision to:
1. Detect and classify vehicles across all intersection approaches.
2. Calculate weighted traffic density in terms of **Passenger Car Units (PCU)** according to standard traffic engineering norms.
3. Dynamically adjust green signal intervals to clear congested queues faster.
4. Detect emergency vehicles and immediately trigger an **Emergency Vehicle Priority Override (EVPO)** to open safe corridors.
5. Prevent starvation on low-volume lanes using an anti-starvation timeout monitor.
6. Provide a web-based command center dashboard with live video streams, traffic light HUDs, and performance KPIs.

---

## 📐 System Architecture

```text
       +---------------------------------------------------------+
       |   Video Feeds (Camera Streams / Simulator / Videos)     |
       +---------------------------------------------------------+
                                   |
                                   v
       +---------------------------------------------------------+
       |   Vehicle Detection Engine (backend/detection.py)       |
       |   - Ultralytics YOLOv8 / Torchvision / Classical CV     |
       |   - Classify: Car, Bus, Truck, Bike, Ambulance          |
       +---------------------------------------------------------+
                                   |
                                   v
       +---------------------------------------------------------+
       |   Traffic Density Analyzer (backend/traffic_analysis.py)|
       |   - Vehicle counting per approach lane                  |
       |   - PCU weighted queue density & saturation indexing    |
       |   - Congestion classification (Low, Mod, High, Critical)|
       +---------------------------------------------------------+
                                   |
                                   v
       +---------------------------------------------------------+
       |   Intelligent Decision Agent (backend/decision_agent.py)|
       |   - Dynamic Green Time Allocation                       |
       |   - Emergency Priority Override (EVPO) State Machine    |
       |   - Anti-Starvation Fair Queuing Guard                  |
       +---------------------------------------------------------+
                    |                             |
                    v                             v
       +-------------------------+   +---------------------------+
       |  Traffic Signal Lights  |   | Web Dashboard (frontend/) |
       |  (Red / Yellow / Green) |   | - Live Multi-Camera HUD   |
       +-------------------------+   | - Real-Time Control & KPIs|
                                     +---------------------------+
```

---

## 📁 Project Directory Structure

```text
Smart-Traffic-Management/
├── backend/
│   ├── app.py                  # Flask web server & streaming APIs
│   ├── detection.py            # Computer Vision detection engine
│   ├── traffic_analysis.py     # PCU density & queue calculation
│   └── decision_agent.py       # Adaptive signal scheduling agent
├── frontend/
│   ├── index.html              # Command Center single-page dashboard
│   ├── style.css               # Modern dark-theme glassmorphism styling
│   └── script.js               # Real-time state polling & controls
├── simulation/
│   └── traffic_simulator.py    # 4-approach traffic physics & frame renderer
├── videos/                     # Storage for custom test traffic MP4 clips
├── models/                     # Storage for YOLO / custom deep learning weights
├── tests/
│   └── test_traffic_system.py  # Unit & integration test suite
├── results/                    # Exported metrics, logs & screenshots
├── docs/                       # Architecture diagrams & capstone reports
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## 🚀 Key Modules & Capabilities

### 1. Computer Vision Detection (`backend/detection.py`)
- **Multi-backend Support**: Automatically detects and leverages **Ultralytics YOLOv8**, **Torchvision SSDLite320 / Faster R-CNN**, or **OpenCV motion contour detection**.
- **Vehicle Classification**: Distinguishes between Cars, Buses, Trucks, Motorcycles, Bicycles, and Emergency Vehicles.
- **Visual Strobe & Cross Detection**: Real-time heuristic check for emergency flashing sirens and high-saturation medical red crosses.

### 2. Weighted PCU Traffic Density (`backend/traffic_analysis.py`)
In accordance with standard Indian Road Congress (IRC) / international traffic engineering guidelines, vehicle counts are transformed into **Passenger Car Units (PCU)**:
- Car / Taxi: `1.0 PCU`
- Bus: `2.5 PCU`
- Heavy Truck: `3.0 PCU`
- Motorcycle: `0.5 PCU`
- Bicycle: `0.2 PCU`
- Emergency Vehicle: `3.5 PCU` + Emergency Flag

### 3. Intelligent Decision Agent (`backend/decision_agent.py`)
- **Adaptive Green Time**:
  $$\text{Green Duration} = T_{\text{min}} + \left( \frac{\text{PCU}_{\text{lane}}}{\sum \text{PCU}_{\text{all}}} \right) \times (T_{\text{max}} - T_{\text{min}})$$
- **Emergency Priority Override**: Forces a rapid yellow clearance for other directions and grants an immediate green wave to approaching ambulances or fire trucks.
- **Anti-Starvation**: If a low-density lane waits longer than the starvation limit (90 seconds), it receives prioritized service.

### 4. Interactive Command Center Dashboard (`frontend/`)
- Real-time 4-lane video feeds with live bounding boxes, vehicle class badges, and stop line markers.
- Visual traffic light indicators with active color glows and remaining countdown timers.
- KPI cards tracking Total Vehicles, Total PCU Load, Cumulative Wait Time Saved, and Emergency Vehicles Cleared.
- Real-time buttons to simulate **Ambulance Injection**, **Rush Hour Congestion**, and **Manual Override**.

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Virtual environment (recommended)

### 1. Clone & Navigate
```bash
cd Smart-Traffic-Management
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

*(Note: Ultralytics YOLOv8 is optional; if not installed, the built-in Torchvision / Classical CV detector runs seamlessly out of the box).*

---

## 🚦 Running the System

### Start the Application Server
```bash
python backend/app.py
```

### Open the Command Center Dashboard
Open your web browser and navigate to:
```text
http://localhost:5050
```

---

## 🧪 Running the Unit Tests

Execute the comprehensive test suite verifying detection, PCU calculations, decision transitions, and the simulation engine:
```bash
python -m unittest tests/test_traffic_system.py
```

All 10 test cases validate:
- Blank frame handling & annotation drawing.
- Multi-class PCU aggregation & congestion level classification.
- Dynamic green timing calculation within min/max thresholds.
- Emergency vehicle priority override state transitions.
- Multi-lane simulator frame rendering.

---

## 📊 Evaluation & Demo Features

- **Emergency Siren Simulation**: Click the `🚨 Ambulance` button under any camera card to watch the decision agent immediately interrupt the cycle and clear the road.
- **Rush Hour Stress Test**: Click `⚡ Rush Hour` to increase vehicle arrival rate on that approach and observe how the AI agent automatically extends green light duration.
- **Mode Comparison**: Toggle the dropdown between **Adaptive AI (Dynamic PCU)**, **Fixed Cycle (30s Baseline)**, and **Manual Override** to showcase wait-time savings.
