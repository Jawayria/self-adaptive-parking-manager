# Self-Adaptive Smart Parking Lot Manager


**Course:** Software Engineering for Autonomous Systems  
**Team Members:** Jawayria Hashmi, Lameya Islam

An autonomous parking management system that uses the **MAPE-K (Monitor-Analyze-Plan-Execute-Knowledge)** control loop to dynamically optimize parking operations. The system monitors parking lot conditions in real-time and autonomously adapts pricing, gate control to maintain optimal utilization, minimize congestion, and maximize revenue.


---

## Features

- **Autonomous Operation** - Fully self-adaptive system with no manual intervention
- **Dynamic Pricing** - Automatic price adjustments based on occupancy ($2-$20 range)
- **Automated Gate Control** - Opens/closes gates to prevent queue overflow
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
docker-compose up -d
```
Verify all services are running: 
```bash
docker ps
```

### 2. Install Python Dependencies (Recommended)

```bash
python -m venv .venv
```
Activate the env (In Windows):
```bash
.venv\Scripts\activate
```
(In Linux/Mac):
```bash
source .venv/bin/activate
```

Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the System

```bash
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
Ctrl+C
docker-compose down -v
```

---

## Project Structure

```
Autonomous_project/
├── config/
│   └── config.yaml              
├── src/
│   ├── models.py                
│   ├── mqtt_client.py           
│   ├── knowledge_base.py        
│   ├── parking_simulator.py     
│   └── autonomic_manager.py     
├── grafana/
│   ├── provisioning/            
│   └── dashboards/
│       └── parking_dashboard.json  
├── docker-compose.yml           
├── requirements.txt             
├── main.py                      
└── README.md                    
```

---

## Configuration

Edit [config/config.yaml](config/config.yaml) to customize parameters.



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

