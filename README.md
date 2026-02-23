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
docker-compose up -d --build
```
Verify all services are running: 
```bash
docker ps
```

### 2. Access Dashboard

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana Dashboard** | http://localhost:3000 | admin / adminadmin |
| **InfluxDB UI** | http://localhost:8086 | admin / adminpassword123 |

**Dashboard Setup**:
1. Login to Grafana
2. Navigate to **Dashboards → Browse**
3. Select **"Smart Parking Lot Manager"**
4. Set time range to **"Last 5 minutes"** for live data


### 3. Stopping the System

```bash
Ctrl+C
docker-compose down -v
```

---

## Project Structure

```
self-adaptive-parking-manager/
├── config/
│   └── config.yaml              # Application configuration
├── services/
│   ├── monitor/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py              # Monitor service
│   ├── analyzer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py              # Analyzer service
│   ├── planner/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py              # Planner service
│   ├── executor/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py              # Executor service
│   └── simulator/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── main.py              # Simulator service
├── src/
│   ├── models.py                # Shared data models
│   ├── mqtt_client.py           # MQTT client wrapper
│   ├── knowledge_base.py        # InfluxDB interface
│   └── parking_simulator.py     # Parking lot simulation
├── grafana/
│   ├── provisioning/            
│   └── dashboards/
│       └── parking_dashboard.json  
├── docker-compose.yml           
├── Project_report.pdf             
├── .gitignore                      
└── README.md                    
```

---

## Configuration

Edit [config/config.yaml](config/config.yaml) to customize parameters.



---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Monitor Service | Python (Docker) | Collects sensor data, calculates metrics |
| Analyzer Service | Python (Docker) | Analyzes state, detects issues |
| Planner Service | Python (Docker) | Creates adaptation decisions |
| Executor Service | Python (Docker) | Sends control commands |
| Message Broker | MQTT (Mosquitto) | Asynchronous inter-service communication |
| Knowledge Base | InfluxDB | Time-series data storage |
| Dashboard | Grafana | Real-time visualization |
| Parking Simulator | Python | Simulates parking lot behavior |

---

## Documentation

For detailed technical documentation, architecture design, MAPE-K implementation, testing results, and academic references, see:

**[Project_report.pdf](Project_report.pdf)**

