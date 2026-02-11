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

**[Project_report.pdf](Project_report.pdf)**

