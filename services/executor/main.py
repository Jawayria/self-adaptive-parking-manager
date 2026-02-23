"""
Executor Service for Self-Adaptive Smart Parking Lot Manager

This service implements the EXECUTE component of the MAPE-K loop:
- Subscribes to adaptation decisions from Planner service
- Creates control commands with appropriate parameters
- Publishes commands to parking lot simulators
- Stores adaptation decisions in InfluxDB
"""

import sys
import signal
import logging
import time
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import (
    AdaptationAction,
    AdaptationDecision,
    ControlCommand,
    ParkingLotConfig
)
from src.mqtt_client import MQTTClient
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Executor Service - Fourth component of MAPE-K loop.
    
    Responsibilities:
    - Subscribe to mape/decision/{lot_id} from Planner
    - Create control commands with parameters (price values, etc.)
    - Publish ControlCommand to parking/lot/{lot_id}/control
    - Store adaptation decisions in InfluxDB
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize MQTT client
        mqtt_config = config['mqtt']
        self.mqtt_client = MQTTClient(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            client_id="mape_executor_service"
        )
        
        # Initialize Knowledge Base for storing decisions
        influx_config = config['influxdb']
        self.knowledge = KnowledgeBase(
            url=influx_config['url'],
            token=influx_config['token'],
            org=influx_config['org'],
            bucket=influx_config['bucket']
        )
        
        # Store lot configs
        self.lot_configs: Dict[str, ParkingLotConfig] = {
            lot['id']: ParkingLotConfig.from_dict(lot)
            for lot in config['parking_lots']
        }
        
        # Adaptation thresholds for command parameters
        self.thresholds = config.get('adaptation', {})
        
        self._running = False
        
        logger.info("Executor Service initialized")
    
    def _on_adaptation_decision(self, topic: str, payload: Dict[str, Any]):
        """Process adaptation decisions from Planner service."""
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            decision = AdaptationDecision.from_dict(payload)
            
            # Execute the decision
            self._execute(decision)
            
            logger.info(
                f"Executor: {decision.lot_id} - Executed actions: "
                f"{[a.value for a in decision.actions]}"
            )
            
        except Exception as e:
            logger.error(f"Executor: Error processing decision: {e}", exc_info=True)
    
    def _execute(self, decision: AdaptationDecision):
        """Execute planned adaptations by sending MQTT control commands."""
        lot_config = self.lot_configs.get(decision.lot_id)
        
        if not lot_config:
            logger.warning(f"Executor: No config found for lot {decision.lot_id}")
            return
        
        control_topic = f"parking/lot/{decision.lot_id}/control"
        
        for action in decision.actions:
            command = self._create_command(
                action=action,
                lot_id=decision.lot_id,
                config=lot_config,
                current_state=decision.current_state,
                reason=decision.trigger_condition
            )
            
            if command:
                self.mqtt_client.publish(control_topic, command.to_dict())
                logger.info(f"Executor: Sent {action.value} command to {decision.lot_id}")
        
        # Store adaptation decision in InfluxDB
        self.knowledge.store_adaptation_decision(decision)
    
    def _create_command(
        self,
        action: AdaptationAction,
        lot_id: str,
        config: ParkingLotConfig,
        current_state: Dict[str, Any],
        reason: str
    ) -> Optional[ControlCommand]:
        """Create a control command for an action."""
        parameters: Dict[str, Any] = {}
        
        current_price = current_state.get("current_price", config.base_price)
        occupancy_pct = current_state.get("occupancy_percentage", 0)
        
        if action == AdaptationAction.INCREASE_PRICE:
            step = self.thresholds.get("price_increase_step", 1.0)
            if occupancy_pct >= 98:
                step *= self.thresholds.get("critical_price_multiplier", 1.5)
            
            new_price = min(current_price + step, config.max_price)
            parameters["new_price"] = round(new_price, 2)
        
        elif action == AdaptationAction.DECREASE_PRICE:
            step = self.thresholds.get("price_decrease_step", 0.5)
            new_price = max(current_price - step, config.min_price)
            parameters["new_price"] = round(new_price, 2)
        
        # Gate actions don't need parameters
        
        return ControlCommand(
            lot_id=lot_id,
            action=action,
            parameters=parameters,
            timestamp=datetime.now(),
            reason=reason
        )
    
    def start(self):
        """Start the Executor service."""
        logger.info("Starting Executor Service...")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        self.mqtt_client.start()
        
        # Wait for connection
        time.sleep(2)
        
        # Subscribe to decisions from Planner
        decision_topic = "mape/decision/+"
        self.mqtt_client.subscribe(decision_topic, self._on_adaptation_decision)
        logger.info(f"Executor: Subscribed to {decision_topic}")
        
        self._running = True
        logger.info("Executor Service started successfully")
    
    def stop(self):
        """Stop the Executor service."""
        logger.info("Stopping Executor Service...")
        self._running = False
        self.mqtt_client.stop()
        self.mqtt_client.disconnect()
        self.knowledge.close()
        logger.info("Executor Service stopped")
    
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
    """Main entry point for Executor service."""
    config = load_config()
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("MAPE-K Executor Service")
    logger.info("=" * 60)
    
    service = ExecutorService(config)
    
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
