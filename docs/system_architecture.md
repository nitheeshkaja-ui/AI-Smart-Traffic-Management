# System Architecture & Technical Specifications

**Project Title**: AI-Based Smart Traffic Management System Using Computer Vision  
**Domain**: Computer Vision, Autonomous Systems & Smart Cities  

---

## 1. Mathematical Models & Equations

### 1.1 Passenger Car Unit (PCU) Equivalents
Traffic composition is heterogeneous. To standardize traffic density, vehicle counts are translated to Passenger Car Units:

$$\text{PCU}_{\text{total}} = \sum_{i \in \text{Classes}} N_i \times W_i$$

Where:
- $N_i$ = Count of vehicle type $i$
- $W_i$ = Equivalent PCU weight:
  - Car / Van: $1.0$
  - Bus: $2.5$
  - Truck: $3.0$
  - Motorcycle: $0.5$
  - Bicycle: $0.2$
  - Emergency (Ambulance): $3.5$

### 1.2 Congestion Ratio & Saturation
Lane saturation percentage $S_{\text{lane}}$ is defined as:

$$S_{\text{lane}} = \min\left(100\%, \frac{\text{PCU}_{\text{total}}}{C_{\text{max}}} \times 100\%\right)$$

Where $C_{\text{max}}$ is the nominal storage capacity of the detection zone (default = 20 PCU).

### 1.3 Dynamic Green Signal Time Allocation
Rather than a static split, green duration $G_j$ for approach $j$ is calculated dynamically:

$$G_j = G_{\text{min}} + \left(\frac{\text{PCU}_j}{\sum_{k=1}^M \text{PCU}_k}\right) \times (G_{\text{max}} - G_{\text{min}})$$

Subject to boundary constraints:
$$G_{\text{min}} \le G_j \le G_{\text{max}}$$

Where:
- $G_{\text{min}} = 10\text{ seconds}$
- $G_{\text{max}} = 50\text{ seconds}$
- $M = 4\text{ approaches (North, South, East, West)}$

---

## 2. Finite State Machine (FSM)

The intersection transitions through the following phases:

1. **`GREEN` Phase**:
   - Signal is green for active approach $j$.
   - Duration determined dynamically by the PCU formula.
   - Constantly polls for emergency vehicle interrupts.

2. **`YELLOW` Phase**:
   - Fixed clearance interval (3-4 seconds).
   - Allows moving vehicles within the intersection boundary to safely vacate.

3. **`ALL_RED` Phase**:
   - Safety buffer (1-2 seconds) where all approaches show RED.
   - Prepares the next approach for safe passage.

4. **`EMERGENCY_OVERRIDE` Phase**:
   - Instantly interrupts current `GREEN`.
   - Forces rapid `YELLOW` clearance for active lane.
   - Immediately routes `GREEN` wave to the designated emergency corridor.

---

## 3. Communication & Data Flow

```text
[Camera/Simulator Frame]
         │
         ▼
[Vehicle Detector (YOLOv8 / Torchvision / Contours)]
         │
         ▼ (Bounding Boxes, Confidences, Centroids)
[Traffic Analyzer (PCU & Congestion Engine)]
         │
         ▼ (Lane PCU, Emergency Flag, Queue Counts)
[Traffic Decision Agent (FSM & Dynamic Scheduler)]
         │
         ▼ (Signal Phase, Green Countdown, System Stats)
[Flask REST API & MJPEG Streamer (app.py)]
         │
         ▼ (HTTP Polling & MJPEG Stream)
[Command Center Web UI (index.html / script.js)]
```
