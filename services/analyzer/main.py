"""
Analyzer Service for Self-Adaptive Smart Parking Lot Manager

This service implements the ANALYZE component of the MAPE-K loop:
- Subscribes to sensor data from Monitor service
- Analyzes parking lot state against thresholds
- Detects issues (high/low occupancy, gate policy violations)
- Publishes AnalysisResult to downstream Planner service
"""

import sys
import signal
import logging
import time
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import SensorData, AdaptationAction, AnalysisResult, ParkingLotConfig
from src.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class AnalyzerService:
    """
    Analyzer Service - Second component of MAPE-K loop.
    
    Responsibilities:
    - Subscribe to mape/sensor_data/{lot_id} from Monitor
    - Analyze parking lot state against thresholds
    - Detect issues and recommend actions
    - Publish AnalysisResult to mape/analysis/{lot_id} for Planner
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize MQTT client
        mqtt_config = config['mqtt']
        self.mqtt_client = MQTTClient(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            client_id="mape_analyzer_service"
        )
        
        # Store lot configs
        self.lot_configs: Dict[str, ParkingLotConfig] = {
            lot['id']: ParkingLotConfig.from_dict(lot)
            for lot in config['parking_lots']
        }
        
        # Adaptation thresholds
        self.thresholds = config.get('adaptation', {})
        
        self._running = False
        
        logger.info("Analyzer Service initialized")
    
    def _on_sensor_data(self, topic: str, payload: Dict[str, Any]):
        """Process sensor data from Monitor service."""
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
            
            # Analyze the sensor data
            analysis = self._analyze(sensor_data)
            
            if analysis:
                # Publish to Planner service
                mape_topic = f"mape/analysis/{sensor_data.lot_id}"
                self.mqtt_client.publish(mape_topic, analysis.to_dict())
                
                logger.info(
                    f"Analyzer: {sensor_data.lot_id} - Issues: {analysis.issues_detected} "
                    f"-> Published to {mape_topic}"
                )
            else:
                logger.debug(f"Analyzer: {sensor_data.lot_id} - No issues detected")
            
        except Exception as e:
            logger.error(f"Analyzer: Error processing sensor data: {e}", exc_info=True)
    
    def _analyze(self, sensor_data: SensorData) -> Optional[AnalysisResult]:
        """
        Analyze current state and recommend actions.
        
        Gate policy (only occupancy-based):
        - Close gate when occupancy >= gate_close_occupancy_threshold
        - Open gate when occupancy < gate_reopen_occupancy
        """
        lot_id = sensor_data.lot_id
        lot_config = self.lot_configs.get(lot_id)
        
        if not lot_config:
            logger.warning(f"Analyzer: No config found for lot {lot_id}")
            return None
        
        issues: List[str] = []
        recommended_actions: List[AdaptationAction] = []
        severity = "low"
        confidence = 0.7
        
        occupancy_pct = sensor_data.occupancy_percentage / 100.0  # 0..1
        
        # Thresholds
        critical_occ = self.thresholds.get("critical_occupancy_threshold", 0.98)
        high_occ = self.thresholds.get("high_occupancy_threshold", 0.85)
        low_occ = self.thresholds.get("low_occupancy_threshold", 0.50)
        gate_close_occ = self.thresholds.get("gate_close_occupancy_threshold", high_occ)
        gate_reopen_occ = self.thresholds.get("gate_reopen_occupancy", 0.80)
        
        # -------------------------
        # Pricing / severity logic
        # -------------------------
        if occupancy_pct >= critical_occ:
            issues.append("CRITICAL: Parking lot at capacity")
            severity = "critical"
            confidence = 0.95
            recommended_actions.append(AdaptationAction.INCREASE_PRICE)
        
        elif occupancy_pct >= high_occ:
            issues.append(f"High occupancy: {occupancy_pct*100:.1f}%")
            severity = "high"
            confidence = 0.85
            recommended_actions.append(AdaptationAction.INCREASE_PRICE)
        
        elif occupancy_pct <= low_occ:
            issues.append(f"Low occupancy: {occupancy_pct*100:.1f}%")
            severity = "medium"
            confidence = 0.80
            recommended_actions.append(AdaptationAction.DECREASE_PRICE)
        
        # -------------------------
        # Gate policy (only occupancy)
        # -------------------------
        if occupancy_pct >= gate_close_occ and sensor_data.gate_state == "open":
            issues.append(
                f"Gate close policy: occupancy {occupancy_pct*100:.1f}% >= {gate_close_occ*100:.1f}%"
            )
            if AdaptationAction.CLOSE_GATE not in recommended_actions:
                recommended_actions.append(AdaptationAction.CLOSE_GATE)
            if severity != "critical":
                severity = "high"
            confidence = min(confidence + 0.1, 1.0)
        
        if occupancy_pct < gate_reopen_occ and sensor_data.gate_state == "closed":
            issues.append(
                f"Gate reopen policy: occupancy {occupancy_pct*100:.1f}% < {gate_reopen_occ*100:.1f}%"
            )
            if AdaptationAction.OPEN_GATE not in recommended_actions:
                recommended_actions.append(AdaptationAction.OPEN_GATE)
        
        # -------------------------
        # Price bounds enforcement
        # -------------------------
        if (sensor_data.current_price >= lot_config.max_price and
                AdaptationAction.INCREASE_PRICE in recommended_actions):
            recommended_actions.remove(AdaptationAction.INCREASE_PRICE)
            issues.append("Price at maximum - cannot increase further")
        
        if (sensor_data.current_price <= lot_config.min_price and
                AdaptationAction.DECREASE_PRICE in recommended_actions):
            recommended_actions.remove(AdaptationAction.DECREASE_PRICE)
            issues.append("Price at minimum - cannot decrease further")
        
        if not issues or (not recommended_actions and len(issues) == 0):
            return None
        
        return AnalysisResult(
            lot_id=lot_id,
            issues_detected=issues,
            severity=severity,
            current_state={
                "occupancy_percentage": sensor_data.occupancy_percentage,
                "current_price": sensor_data.current_price,
                "gate_state": sensor_data.gate_state,
                "rejected_count": sensor_data.rejected_count,
                "revenue": sensor_data.revenue
            },
            recommended_actions=recommended_actions,
            confidence=confidence
        )
    
    def start(self):
        """Start the Analyzer service."""
        logger.info("Starting Analyzer Service...")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        self.mqtt_client.start()
        
        # Wait for connection
        time.sleep(2)
        
        # Subscribe to sensor data from Monitor
        sensor_topic = "mape/sensor_data/+"
        self.mqtt_client.subscribe(sensor_topic, self._on_sensor_data)
        logger.info(f"Analyzer: Subscribed to {sensor_topic}")
        
        self._running = True
        logger.info("Analyzer Service started successfully")
    
    def stop(self):
        """Stop the Analyzer service."""
        logger.info("Stopping Analyzer Service...")
        self._running = False
        self.mqtt_client.stop()
        self.mqtt_client.disconnect()
        logger.info("Analyzer Service stopped")
    
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
    """Main entry point for Analyzer service."""
    config = load_config()
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("MAPE-K Analyzer Service")
    logger.info("=" * 60)
    
    service = AnalyzerService(config)
    
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
