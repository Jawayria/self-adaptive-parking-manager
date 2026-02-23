"""
Monitor Service for Self-Adaptive Smart Parking Lot Manager

This service implements the MONITOR component of the MAPE-K loop:
- Subscribes to parking lot sensor data via MQTT
- Stores sensor data in InfluxDB (Knowledge Base)
- Calculates and stores system-wide metrics
- Publishes sensor data to downstream Analyzer service
"""

import sys
import signal
import logging
import time
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import SensorData, SystemMetrics, ParkingLotConfig
from src.mqtt_client import MQTTClient
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class MonitorService:
    """
    Monitor Service - First component of MAPE-K loop.
    
    Responsibilities:
    - Subscribe to parking/lot/+/sensors for raw sensor data
    - Store sensor data in InfluxDB
    - Calculate system-wide metrics
    - Publish processed data to mape/sensor_data/{lot_id} for Analyzer
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize MQTT client
        mqtt_config = config['mqtt']
        self.mqtt_client = MQTTClient(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            client_id="mape_monitor_service"
        )
        
        # Initialize Knowledge Base
        influx_config = config['influxdb']
        self.knowledge = KnowledgeBase(
            url=influx_config['url'],
            token=influx_config['token'],
            org=influx_config['org'],
            bucket=influx_config['bucket']
        )
        
        # Store lot configs for metrics calculation
        self.lot_configs = {
            lot['id']: ParkingLotConfig.from_dict(lot)
            for lot in config['parking_lots']
        }
        
        # Track current states for metrics calculation
        self._current_states: Dict[str, SensorData] = {}
        
        # Adaptation thresholds for metrics
        self._adaptation_thresholds = config.get('adaptation', {})
        
        self._running = False
        
        logger.info("Monitor Service initialized")
    
    def _on_sensor_data(self, topic: str, payload: Dict[str, Any]):
        """Process incoming sensor data from parking lot simulators."""
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            sensor_data = SensorData(
                lot_id=payload["lot_id"],
                occupancy_percentage=payload["occupancy_percentage"],
                current_occupancy=payload["current_occupancy"],
                total_capacity=payload["total_capacity"],
                queue_length=payload.get("queue_length", 0),
                rejected_count=payload["rejected_count"],
                current_price=payload["current_price"],
                gate_state=payload["gate_state"],
                revenue=payload["revenue"],
                external_traffic_level=payload.get("external_traffic_level", 0.5),
                timestamp=datetime.fromisoformat(payload["timestamp"]) if "timestamp" in payload else datetime.now()
            )
            
            # Store in InfluxDB
            self.knowledge.store_sensor_data(sensor_data)
            
            # Update local state cache for metrics
            self._current_states[sensor_data.lot_id] = sensor_data
            
            # Calculate and store system metrics
            self._update_system_metrics()
            
            # Publish to Analyzer service
            mape_topic = f"mape/sensor_data/{sensor_data.lot_id}"
            self.mqtt_client.publish(mape_topic, sensor_data.to_dict())
            
            logger.info(
                f"Monitor: Processed {sensor_data.lot_id} - "
                f"Occupancy: {sensor_data.occupancy_percentage:.1f}% -> Published to {mape_topic}"
            )
            
        except Exception as e:
            logger.error(f"Monitor: Error processing sensor data: {e}", exc_info=True)
    
    def _update_system_metrics(self):
        """Calculate and store system-wide metrics."""
        if not self._current_states:
            return
        
        all_states = self._current_states
        thresholds = self._adaptation_thresholds
        
        total_revenue = sum(s.revenue for s in all_states.values())
        total_occupancy = sum(s.current_occupancy for s in all_states.values())
        total_capacity = sum(s.total_capacity for s in all_states.values())
        total_rejected = sum(s.rejected_count for s in all_states.values())
        total_queue = sum(getattr(s, "queue_length", 0) for s in all_states.values())
        avg_price = sum(s.current_price for s in all_states.values()) / len(all_states)
        
        lots_at_capacity = sum(1 for s in all_states.values() if s.occupancy_percentage >= 95)
        lots_under_utilized = sum(
            1 for s in all_states.values()
            if s.occupancy_percentage < thresholds.get("low_occupancy_threshold", 0.50) * 100
        )
        
        metrics = SystemMetrics(
            timestamp=datetime.now(),
            total_revenue=total_revenue,
            total_occupancy=total_occupancy,
            total_capacity=total_capacity,
            total_rejected=total_rejected,
            total_queue_length=total_queue,
            average_price=avg_price,
            lots_at_capacity=lots_at_capacity,
            lots_under_utilized=lots_under_utilized
        )
        
        # Store in InfluxDB
        self.knowledge.store_system_metrics(metrics)
        
        # Publish system metrics
        self.mqtt_client.publish("parking/system/metrics", metrics.to_dict())
    
    def start(self):
        """Start the Monitor service."""
        logger.info("Starting Monitor Service...")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        self.mqtt_client.start()
        
        # Wait for connection
        time.sleep(2)
        
        # Subscribe to sensor data from all parking lots
        sensor_topic = "parking/lot/+/sensors"
        self.mqtt_client.subscribe(sensor_topic, self._on_sensor_data)
        logger.info(f"Monitor: Subscribed to {sensor_topic}")
        
        self._running = True
        logger.info("Monitor Service started successfully")
    
    def stop(self):
        """Stop the Monitor service."""
        logger.info("Stopping Monitor Service...")
        self._running = False
        self.mqtt_client.stop()
        self.mqtt_client.disconnect()
        self.knowledge.close()
        logger.info("Monitor Service stopped")
    
    def run(self):
        """Run the service until interrupted."""
        self.start()
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    """Configure logging."""
    log_config = config.get('logging', {})
    level = getattr(logging, log_config.get('level', 'INFO'))
    format_str = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler()]
    )


def main():
    """Main entry point for Monitor service."""
    config = load_config()
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("MAPE-K Monitor Service")
    logger.info("=" * 60)
    
    service = MonitorService(config)
    
    # Graceful shutdown handler
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal")
        service.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    service.run()


if __name__ == "__main__":
    main()
