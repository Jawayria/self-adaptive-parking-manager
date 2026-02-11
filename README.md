# Self-Adaptive Smart Parking Lot Manager


**Course:** Software Engineering for Autonomous Systems  
**Team Members:** Jawayria Hashmi, Lameya Islam

An autonomous parking management system that uses the **MAPE-K (Monitor-Analyze-Plan-Execute-Knowledge)** control loop to dynamically optimize parking operations. The system monitors parking lot conditions in real-time and autonomously adapts pricing, gate control, and vehicle redirection to maintain optimal utilization, minimize congestion, and maximize revenue.


---

## Features

- **Autonomous Operation** - Fully self-adaptive system with no manual intervention
- **Dynamic Pricing** - Automatic price adjustments based on occupancy ($2-$20 range)
- **Automated Gate Control** - Opens/closes gates to prevent queue overflow
- **Vehicle Redirection** - Load balancing across multiple parking lots
- **Real-time Dashboard** - Live monitoring with Grafana visualization
- **MAPE-K Architecture** - Complete autonomic computing implementation
- **Containerized Infrastructure** - Docker-based deployment (MQTT, InfluxDB, Grafana)

---

## MAPE-K Implementation

The system manages **2 parking lots** (Lot 1: 100 spaces, Lot 2: 50 spaces) using:

- **Monitor**: Collects sensor data via MQTT
- **Analyze**: Detects congestion, under-utilization, and threshold violations
- **Plan**: Selects optimal adaptation actions with cooldown logic
- **Execute**: Sends control commands to parking lot effectors
- **Knowledge**: Stores historical data and decisions in InfluxDB

---

## Quick Start

### 1. Start Infrastructure

```bash
# Start Docker services (MQTT, InfluxDB, Grafana)
docker-compose up -d

# Verify containers are running
docker ps
```

### 2. Install Python Dependencies

```bash
# Create and activate virtual environment (recommended)
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the System

```bash
# Run full MAPE-K implementation
python main.py
```

Expected output:
```
============================================================
Self-Adaptive Smart Parking Lot Manager
============================================================
INFO - MQTT Client connected
INFO - InfluxDB connected  
INFO - Starting parking simulators...
INFO - Starting autonomic manager...
INFO - MAPE-K [lot_1]: Analysis detected HIGH_OCCUPANCY
INFO - Executed increase_price for lot_1
```

### 4. Access Dashboard

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana Dashboard** | http://localhost:3000 | admin / adminadmin |
| **InfluxDB UI** | http://localhost:8086 | admin / adminpassword123 |

**Dashboard Setup**:
1. Login to Grafana
2. Navigate to **Dashboards → Browse**
3. Select **"Smart Parking Lot Manager"**
4. Set time range to **"Last 5 minutes"** for live data


### 5. Stopping the System

```bash
# Stop Python application
Ctrl+C

# Stop Docker containers
docker-compose down

# Remove all data (fresh start)
docker-compose down -v
```

---

## Project Structure

```
Autonomous_project/
├── config/
│   └── config.yaml              # System configuration & thresholds
├── src/
│   ├── models.py                # Data models (SensorData, ControlCommand)
│   ├── mqtt_client.py           # MQTT communication wrapper
│   ├── knowledge_base.py        # InfluxDB integration (Knowledge component)
│   ├── parking_simulator.py     # Parking lot simulation
│   └── autonomic_manager.py     # MAPE-K loop implementation
├── grafana/
│   ├── provisioning/            # Auto-configured datasources
│   └── dashboards/
│       └── parking_dashboard.json  # Pre-built dashboard
├── docker-compose.yml           # Infrastructure setup
├── requirements.txt             # Python dependencies
├── main.py                      # Main entry point
└── README.md                    # This file
```

---

## Configuration

Edit [config/config.yaml](config/config.yaml) to customize behavior:

```yaml
# Parking lot settings
parking_lots:
  - id: "lot_1"
    total_capacity: 100
    base_price: 5.0
    min_price: 2.0
    max_price: 20.0

# Simulation parameters  
simulation:
  base_arrival_rate: 0.5        # 50% probability per tick
  base_departure_rate: 0.15     # 15% probability per tick
  peak_hours: [8, 9, 12, 13, 17]

# Adaptation thresholds
adaptation:
  high_occupancy_threshold: 0.90    # Trigger price increase at 90%
  low_occupancy_threshold: 0.50     # Trigger price decrease at 50%
  gate_close_queue_threshold: 8     # Close gate when queue >= 8
  gate_reopen_occupancy: 0.85       # Reopen gate when occupancy < 85%
  price_increase_step: 1.0          # $1.00 increase
  price_decrease_step: 0.5          # $0.50 decrease
```

---

## Troubleshooting

**Dashboard shows "No Data":**
- Ensure `main.py` is running
- Verify Grafana time range is "Last 5 minutes"

**MQTT Connection Failed:**
- Check Mosquitto is running: `docker ps | grep mosquitto`
- Verify port 1883 is available

**InfluxDB Connection Error:**
- Check InfluxDB health: `curl http://localhost:8086/health`
- Verify credentials in config.yaml match docker-compose.yml

---

## System Metrics

| Goal | Target | 
|------|--------|
| Utilization | 70-95% | 
| Queue Length | < 8 vehicles | 
| Response Time | < 2 sec |
| Adaptation | Autonomous | 

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Autonomic Manager | Python | MAPE-K control loop implementation |
| Message Broker | MQTT (Mosquitto) | Asynchronous communication |
| Knowledge Base | InfluxDB | Time-series data storage |
| Dashboard | Grafana | Real-time visualization |
| Parking Simulator | Python | Simulates parking lot behavior |

---

## Documentation

For detailed technical documentation, architecture design, MAPE-K implementation, testing results, and academic references, see:

**[PROJECT_REPORT.md](PROJECT_REPORT.md)**



## 2. System Goals and Objectives

### 2.1 Primary Goals

| Goal ID | Description | Metric | Target |
|---------|-------------|--------|--------|
| 1 | Maintain optimal utilization | Occupancy % | 70-95% |
| 2 | Minimize congestion | Queue length | < 8 vehicles |
| 3 | Reduce rejections | Rejected count | Minimize |
| 4 | Maximize revenue | Total revenue | Maximize |
| 5 | System responsiveness | Adaptation latency | < 2 sec |

### 2.2 Adaptation Objectives

1. **Dynamic Pricing**: Adjust prices based on occupancy levels
   - Increase price when occupancy > 90% (discourage arrivals)
   - Decrease price when occupancy < 50% (attract customers)

2. **Gate Control**: Manage vehicle flow automatically
   - Close gate when queue ≥ 8 vehicles (prevent overflow)
   - Reopen gate when occupancy drops below 85%

3. **Vehicle Redirection**: Balance load across lots
   - Redirect vehicles when one lot reaches 98% capacity
   - Direct to alternative lot with lower occupancy

---

## 3. Architecture Design

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AUTONOMIC MANAGER                                  │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐         │
│  │  MONITOR   │ → │  ANALYZE   │ → │    PLAN    │ → │  EXECUTE   │         │
│  │            │   │            │   │            │   │            │         │
│  │ - Subscribe│   │ - Detect   │   │ - Select   │   │ - Send     │         │
│  │   to MQTT  │   │   issues   │   │   actions  │   │   commands │         │
│  │ - Collect  │   │ - Evaluate │   │ - Predict  │   │ - Log      │         │
│  │   sensor   │   │   severity │   │   outcomes │   │   decisions│         │
│  │   data     │   │            │   │            │   │            │         │
│  └─────┬──────┘   └──────┬─────┘   └──────┬─────┘   └─────┬──────┘         │
│        │                 │                │               │                 │
│        │         ┌───────┴────────────────┴───────┐      │                 │
│        └────────►│         KNOWLEDGE BASE         │◄─────┘                 │
│                  │          (InfluxDB)            │                         │
│                  │  - Historical sensor data      │                         │
│                  │  - Adaptation decisions        │                         │
│                  │  - Configuration parameters    │                         │
│                  │  - Decision rules              │                         │
│                  └────────────────────────────────┘                         │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │ MQTT Pub/Sub
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  PARKING LOT 1  │   │  PARKING LOT 2  │   │    GRAFANA      │
│  (Main - 100)   │   │ (Overflow - 50) │   │   DASHBOARD     │
│                 │   │                 │   │                 │
│ ┌─────────────┐ │   │ ┌─────────────┐ │   │ - Real-time     │
│ │   Sensors   │ │   │ │   Sensors   │ │   │   visualization │
│ │ - Occupancy │ │   │ │ - Occupancy │ │   │ - Trend graphs  │
│ │ - Queue     │ │   │ │ - Queue     │ │   │ - Alerts        │
│ │ - Revenue   │ │   │ │ - Revenue   │ │   │ - Adaptation    │
│ └─────────────┘ │   │ └─────────────┘ │   │   history       │
│ ┌─────────────┐ │   │ ┌─────────────┐ │   └─────────────────┘
│ │  Effectors  │ │   │ │  Effectors  │ │
│ │ - Gate      │ │   │ │ - Gate      │ │
│ │ - Price     │ │   │ │ - Price     │ │
│ │   Display   │ │   │ │   Display   │ │
│ └─────────────┘ │   │ └─────────────┘ │
└─────────────────┘   └─────────────────┘
```

### 3.2 Component Description

| Component | Technology | Purpose |
|-----------|------------|---------|
| Autonomic Manager | Python | MAPE-K control loop implementation |
| Message Broker | MQTT (Mosquitto) | Asynchronous communication |
| Knowledge Base | InfluxDB | Time-series data storage |
| Dashboard | Grafana | Real-time visualization |
| Parking Simulator | Python | Simulates parking lot behavior |

---

## 4. MAPE-K Loop Implementation

### 4.1 Monitor Component

**Purpose**: Collect real-time sensor data from all parking lots

**Implementation**:
```python
# MQTT Topics Subscribed
parking/lot/{lot_id}/sensors    # Sensor readings
parking/system/metrics          # System-wide metrics
```

**Data Collected**:
| Field | Type | Description |
|-------|------|-------------|
| occupancy_percentage | Float | Current lot utilization (0-100%) |
| current_occupancy | Integer | Number of parked vehicles |
| queue_length | Integer | Vehicles waiting at entrance |
| rejected_count | Integer | Cumulative rejected vehicles |
| current_price | Float | Current parking rate |
| gate_state | String | "open" or "closed" |
| revenue | Float | Cumulative revenue |
| external_traffic_level | Float | Simulated traffic intensity |

### 4.2 Analyze Component

**Purpose**: Detect deviations from system goals and assess severity

**Analysis Rules**:

| Condition | Severity | Issue Detected |
|-----------|----------|----------------|
| Occupancy > 98% | Critical | Capacity overload |
| Occupancy > 90% | High | High congestion |
| Queue ≥ 8 | High | Entrance congestion |
| Occupancy < 50% | Medium | Underutilization |
| Queue ≥ 5 | Low | Queue building |

**Implementation Logic**:
```python
def analyze(self, lot_id: str) -> AnalysisResult:
    state = self.knowledge_base.get_current_state(lot_id)
    issues = []
    
    if state.occupancy_percentage > 98:
        issues.append("CRITICAL_OCCUPANCY")
        severity = "critical"
    elif state.occupancy_percentage > 90:
        issues.append("HIGH_OCCUPANCY")
        severity = "high"
    elif state.queue_length >= 8:
        issues.append("HIGH_QUEUE")
        severity = "high"
    # ... additional rules
    
    return AnalysisResult(lot_id, issues, severity, state)
```

### 4.3 Plan Component

**Purpose**: Select appropriate adaptation actions based on analysis

**Decision Matrix**:

| Trigger Condition | Action | Parameters |
|-------------------|--------|------------|
| Occupancy > 90% | INCREASE_PRICE | +$1.00 |
| Occupancy < 50% | DECREASE_PRICE | -$0.50 |
| Queue ≥ 8 | CLOSE_GATE | - |
| Gate closed & Occupancy < 85% | OPEN_GATE | - |
| Occupancy > 98% & Queue > 0 | REDIRECT_VEHICLES | target_lot |

**Cooldown Mechanism**: 10-second cooldown between adaptations per lot to prevent oscillation.

### 4.4 Execute Component

**Purpose**: Apply planned adaptations via MQTT commands

**Command Structure**:
```json
{
  "lot_id": "lot_1",
  "action": "INCREASE_PRICE",
  "parameters": {"new_price": 6.00},
  "timestamp": "2026-02-01T00:25:00Z",
  "reason": "High occupancy detected (92%)"
}
```

**MQTT Topics Published**:
```
parking/lot/{lot_id}/control    # Control commands
parking/system/adaptations      # Adaptation log
```

### 4.5 Knowledge Component

**Purpose**: Persistent storage of system state, history, and rules

**InfluxDB Measurements**:

| Measurement | Fields | Tags |
|-------------|--------|------|
| parking_sensor_data | occupancy, queue, price, revenue | lot_id |
| adaptation_decisions | action, trigger, confidence | lot_id |
| system_metrics | total_utilization, total_revenue | - |

---

## 5. Adaptation Strategies

### 5.1 Dynamic Pricing Strategy

**Objective**: Balance demand through price elasticity

**Algorithm**:
```
IF occupancy > HIGH_THRESHOLD (90%):
    new_price = min(current_price + INCREASE_STEP, MAX_PRICE)
    
ELSE IF occupancy < LOW_THRESHOLD (50%):
    new_price = max(current_price - DECREASE_STEP, MIN_PRICE)
```

**Price Boundaries**:
| Lot | Min Price | Max Price | Base Price |
|-----|-----------|-----------|------------|
| Lot 1 | $2.00 | $20.00 | $5.00 |
| Lot 2 | $1.00 | $15.00 | $3.00 |

### 5.2 Gate Control Strategy

**Objective**: Prevent queue buildup and system overload

**Trigger Conditions**:
- **Close Gate**: Queue length ≥ 8 vehicles
- **Open Gate**: Occupancy drops below 85%

**Behavior When Gate Closed**:
- New arrivals join queue (up to max 15)
- Departures continue normally
- Queue members enter as spaces become available

### 5.3 Vehicle Redirection Strategy

**Objective**: Balance load across multiple lots

**Trigger**: Occupancy ≥ 98% AND queue > 0

**Target Selection**: Lot with occupancy < 85%

### 5.4 Adaptation Effectiveness

The system demonstrates **reactive adaptation** with the following characteristics:

| Metric | Target | Achieved |
|--------|--------|----------|
| Response Time | < 2 sec | ~2 sec |
| Price Oscillation | Minimal | Low (with cooldown) |
| Queue Prevention | Queue < 8 | Triggers gate close |
| Utilization Range | 70-95% | Maintained dynamically |

---

## 6. Implementation Details

### 6.1 Project Structure

```
Autonomous_project/
├── config/
│   └── config.yaml              # System configuration
├── src/
│   ├── __init__.py
│   ├── models.py                # Data models (SensorData, ControlCommand, etc.)
│   ├── mqtt_client.py           # MQTT communication wrapper
│   ├── knowledge_base.py        # InfluxDB integration
│   ├── parking_simulator.py     # Parking lot simulation
│   └── autonomic_manager.py     # MAPE-K implementation
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── datasources.yml  # InfluxDB datasource config
│   │   └── dashboards/
│   │       └── dashboards.yml   # Dashboard provisioning
│   └── dashboards/
│       └── parking_dashboard.json
├── mosquitto/
│   └── config/
│       └── mosquitto.conf       # MQTT broker configuration
├── docker-compose.yml           # Infrastructure setup
├── requirements.txt             # Python dependencies
├── main.py                      # Main entry point
├── write_test_data.py           # Test data generator
└── README.md                    # This report
```

### 9.2 Key Classes

#### MAPEKAutonomicManager
Central controller implementing the MAPE-K loop:
- `_monitor()`: Subscribes to MQTT and collects sensor data
- `_analyze()`: Evaluates state against goals
- `_plan()`: Selects adaptation actions
- `_execute()`: Sends control commands
- `_mape_k_cycle()`: Main control loop (runs every 2 seconds)

#### ParkingLotSimulator
Simulates parking lot dynamics:
- Generates realistic arrival/departure patterns
- Responds to control commands (price changes, gate control)
- Publishes sensor data via MQTT

#### KnowledgeBase
Manages persistent storage in InfluxDB:
- Stores historical sensor data
- Records adaptation decisions
- Provides query interface for analysis

### 9.3 Configuration Parameters

```yaml
adaptation:
  target_utilization_min: 0.70      # 70%
  target_utilization_max: 0.95      # 95%
  high_occupancy_threshold: 0.90    # Trigger price increase
  low_occupancy_threshold: 0.50     # Trigger price decrease
  gate_close_queue_threshold: 8     # Close gate when queue >= 8
  gate_reopen_occupancy: 0.85       # Reopen gate below 85%
  price_increase_step: 1.0          # $1.00 increase
  price_decrease_step: 0.5          # $0.50 decrease
```

---

## 10. Testing and Evaluation

### 10.1 Test Scenarios

#### Scenario 1: High Demand Period
**Input**: Continuous high arrival rate  
**Expected Behavior**:
1. Occupancy rises above 90%
2. System increases price automatically
3. If queue builds to 8+, gate closes
4. Occupancy drops below 85%, gate reopens

**Result**: ✅ System correctly adapts to high demand

#### Scenario 2: Low Demand Period
**Input**: Low arrival rate, high departure rate  
**Expected Behavior**:
1. Occupancy falls below 50%
2. System decreases price to attract customers
3. Price stabilizes at minimum when demand remains low

**Result**: ✅ System correctly reduces prices

#### Scenario 3: Queue Management
**Input**: Full lot with continuous arrivals  
**Expected Behavior**:
1. Queue builds at entrance
2. At queue = 8, gate closes automatically
3. Departures reduce occupancy
4. At occupancy < 85%, gate reopens
5. Queue vehicles enter

**Result**: ✅ Gate control prevents excessive queuing

### 10.2 Metrics Collected

| Metric | Description | Collection Method |
|--------|-------------|-------------------|
| Occupancy % | Current utilization | Real-time sensor |
| Queue Length | Vehicles waiting | Real-time sensor |
| Rejected Count | Turned away vehicles | Cumulative counter |
| Revenue | Total earnings | Cumulative counter |
| Adaptation Count | Number of adaptations | Event log |
| Response Time | Adaptation latency | Timestamp analysis |

---

## 11. Results and Discussion

### 11.1 System Performance

The self-adaptive parking lot manager successfully demonstrates autonomous behavior:

| Goal | Target | Result | Status |
|------|--------|--------|--------|
| Utilization | 70-95% | Maintained within range | ✅ |
| Queue Length | < 8 | Gate closes at threshold | ✅ |
| Rejection Prevention | Minimize | Redirects when full | ✅ |
| Response Time | < 2 sec | ~2 sec cycle time | ✅ |

### 11.2 Adaptation Effectiveness

**Dynamic Pricing**:
- Successfully deters demand when occupancy high
- Attracts customers during low periods
- Price oscillation minimized by cooldown mechanism

**Gate Control**:
- Prevents queue overflow (max observed: 15 vehicles)
- Automatic reopening ensures continuous service
- Balances flow control with customer access

**Redirection**:
- Enables load balancing across lots
- Reduces overall rejection rate
- Improves system-wide utilization

### 11.3 Visualization Dashboard

The Grafana dashboard provides real-time visibility into:

1. **System Overview**
   - Overall utilization gauge (color-coded thresholds)
   - Total revenue counter
   - Combined queue length (both lots)
   - Rejected vehicles count

2. **Per-Lot Status**
   - Gate status (OPEN/CLOSED with color indicators)
   - Individual queue lengths
   - Current price display

3. **Trend Analysis**
   - Occupancy over time (line chart)
   - Dynamic pricing history
   - Queue length patterns
   - Revenue accumulation

4. **Adaptation Log**
   - Recent adaptation decisions table
   - Trigger conditions and actions


## 12. Conclusion

### 12.1 Summary

This project successfully implements a **Self-Adaptive Smart Parking Lot Manager** using the MAPE-K autonomic computing reference architecture. The system demonstrates:

- **Autonomous Operation**: No human intervention required for normal operation
- **Goal-Directed Behavior**: Maintains utilization, minimizes queues, maximizes revenue
- **Reactive Adaptation**: Responds to environmental changes within 2 seconds
- **Observability**: Real-time dashboard provides full system visibility

### 12.3 Future Enhancements

1. **Predictive Adaptation**: Use ML to predict demand and adapt proactively
2. **Multi-Objective Optimization**: Balance competing goals (revenue vs. accessibility)
3. **Historical Pattern Learning**: Adapt thresholds based on historical data
4. **Integration with Real Sensors**: Replace simulation with IoT devices
5. **Mobile App Integration**: Real-time availability and pricing for users

---

## 13. Installation and Usage Guide

### 13.1 Prerequisites

- Docker and Docker Compose
- Python 3.8 or higher
- pip (Python package manager)

### 13.2 Quick Start

#### Step 1: Clone and Navigate
```bash
cd Autonomous_project
```

#### Step 2: Start Infrastructure
```bash
docker-compose up -d
```

This starts:
- **Mosquitto MQTT Broker** on port 1883
- **InfluxDB** on port 8086
- **Grafana** on port 3000

#### Step 3: Install Python Dependencies
```bash
pip install -r requirements.txt
```

#### Step 4: Run the System

**Option A: Full System (Simulator + Manager)**
```bash
python main.py
```

**Option B: Test Data Generator (Dashboard Demo)**
```bash
python write_test_data.py
```

#### Step 5: Access Dashboard

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| InfluxDB | http://localhost:8086 | admin / adminpassword123 |

### 13.3 Stopping the System

```bash
# Stop Python processes
Ctrl+C

# Stop Docker containers
docker-compose down

# Remove all data
docker-compose down -v
```

## 14. References

1. Eclipse Mosquitto. https://mosquitto.org/

2. InfluxDB Documentation. https://docs.influxdata.com/

3. Grafana Documentation. https://grafana.com/docs/

4. Paho MQTT Python Client. https://www.eclipse.org/paho/

---

## Appendix A: MQTT Topic Reference

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `parking/lot/{lot_id}/sensors` | Lot → Manager | Sensor data |
| `parking/lot/{lot_id}/control` | Manager → Lot | Control commands |
| `parking/lot/{lot_id}/status` | Lot → Dashboard | Status updates |
| `parking/system/metrics` | Manager → All | System-wide metrics |
| `parking/system/adaptations` | Manager → Log | Adaptation events |

## Appendix B: InfluxDB Schema

**Measurement: parking_sensor_data**
```
Fields: occupancy_percentage, current_occupancy, total_capacity,
        queue_length, rejected_count, current_price, revenue,
        external_traffic_level, gate_state
Tags: lot_id
```

**Measurement: adaptation_decisions**
```
Fields: action, trigger_condition, confidence, expected_outcome
Tags: lot_id
```

**Measurement: system_metrics**
```
Fields: overall_utilization, total_revenue, total_queue_length,
        total_rejected
```

---

