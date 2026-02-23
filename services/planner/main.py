"""
Planner Service for Self-Adaptive Smart Parking Lot Manager

This service implements the PLAN component of the MAPE-K loop:
- Subscribes to analysis results from Analyzer service
- Checks cooldown period via InfluxDB
- Creates concrete adaptation decisions
- Publishes AdaptationDecision to downstream Executor service
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

from src.models import AdaptationAction, AnalysisResult, AdaptationDecision
from src.mqtt_client import MQTTClient
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class PlannerService:
    """
    Planner Service - Third component of MAPE-K loop.
    
    Responsibilities:
    - Subscribe to mape/analysis/{lot_id} from Analyzer
    - Check cooldown period before planning
    - Create concrete adaptation decisions
    - Publish AdaptationDecision to mape/decision/{lot_id} for Executor
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize MQTT client
        mqtt_config = config['mqtt']
        self.mqtt_client = MQTTClient(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            client_id="mape_planner_service"
        )
        
        # Initialize Knowledge Base for cooldown tracking
        influx_config = config['influxdb']
        self.knowledge = KnowledgeBase(
            url=influx_config['url'],
            token=influx_config['token'],
            org=influx_config['org'],
            bucket=influx_config['bucket']
        )
        
        # Cooldown configuration (seconds)
        self._adaptation_cooldown = 10
        
        self._running = False
        
        logger.info("Planner Service initialized")
    
    def _on_analysis_result(self, topic: str, payload: Dict[str, Any]):
        """Process analysis results from Analyzer service."""
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            analysis = AnalysisResult.from_dict(payload)
            
            # Create adaptation plan
            decision = self._plan(analysis)
            
            if decision:
                # Store cooldown timestamp
                self.knowledge.store_adaptation_timestamp(decision.lot_id)
                
                # Publish to Executor service
                mape_topic = f"mape/decision/{decision.lot_id}"
                self.mqtt_client.publish(mape_topic, decision.to_dict())
                
                logger.info(
                    f"Planner: {decision.lot_id} - Actions: {[a.value for a in decision.actions]} "
                    f"-> Published to {mape_topic}"
                )
            else:
                logger.debug(f"Planner: {analysis.lot_id} - No decision made (cooldown or no actions)")
            
        except Exception as e:
            logger.error(f"Planner: Error processing analysis result: {e}", exc_info=True)
    
    def _plan(self, analysis: AnalysisResult) -> Optional[AdaptationDecision]:
        """Create a concrete adaptation plan from analysis results."""
        if not analysis.recommended_actions:
            return None
        
        # Check cooldown
        last_adaptation_time = self.knowledge.get_last_adaptation_time(analysis.lot_id)
        if last_adaptation_time:
            # Convert to naive datetime for comparison if needed
            if last_adaptation_time.tzinfo is not None:
                from datetime import timezone
                last_adaptation_time = last_adaptation_time.replace(tzinfo=None)
            
            elapsed = (datetime.now() - last_adaptation_time).total_seconds()
            if elapsed < self._adaptation_cooldown:
                logger.debug(
                    f"Planner: Skipping adaptation for {analysis.lot_id} - "
                    f"cooldown active ({elapsed:.1f}s < {self._adaptation_cooldown}s)"
                )
                return None
        
        # Filter conflicting actions
        final_actions: List[AdaptationAction] = []
        for action in analysis.recommended_actions:
            if action == AdaptationAction.OPEN_GATE and AdaptationAction.CLOSE_GATE in final_actions:
                continue
            if action == AdaptationAction.CLOSE_GATE and AdaptationAction.OPEN_GATE in final_actions:
                continue
            if action not in final_actions:
                final_actions.append(action)
        
        if not final_actions:
            return None
        
        decision = AdaptationDecision(
            lot_id=analysis.lot_id,
            timestamp=datetime.now(),
            trigger_condition="; ".join(analysis.issues_detected),
            current_state=analysis.current_state,
            actions=final_actions,
            expected_outcome=self._predict_outcome(final_actions),
            confidence=analysis.confidence
        )
        
        logger.info(f"Planner: Created decision for {analysis.lot_id}")
        logger.info(f"  Issues: {analysis.issues_detected}")
        logger.info(f"  Actions: {[a.value for a in final_actions]}")
        logger.info(f"  Expected outcome: {decision.expected_outcome}")
        
        return decision
    
    def _predict_outcome(self, actions: List[AdaptationAction]) -> str:
        """Predict the expected outcome of the planned actions."""
        outcomes = []
        for action in actions:
            if action == AdaptationAction.INCREASE_PRICE:
                outcomes.append("reduced arrival rate, increased revenue per vehicle")
            elif action == AdaptationAction.DECREASE_PRICE:
                outcomes.append("increased arrival rate, improved utilization")
            elif action == AdaptationAction.CLOSE_GATE:
                outcomes.append("controlled inflow")
            elif action == AdaptationAction.OPEN_GATE:
                outcomes.append("resumed normal operations")
        
        return "; ".join(outcomes)
    
    def start(self):
        """Start the Planner service."""
        logger.info("Starting Planner Service...")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        self.mqtt_client.start()
        
        # Wait for connection
        time.sleep(2)
        
        # Subscribe to analysis results from Analyzer
        analysis_topic = "mape/analysis/+"
        self.mqtt_client.subscribe(analysis_topic, self._on_analysis_result)
        logger.info(f"Planner: Subscribed to {analysis_topic}")
        
        self._running = True
        logger.info("Planner Service started successfully")
    
    def stop(self):
        """Stop the Planner service."""
        logger.info("Stopping Planner Service...")
        self._running = False
        self.mqtt_client.stop()
        self.mqtt_client.disconnect()
        self.knowledge.close()
        logger.info("Planner Service stopped")
    
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
    """Main entry point for Planner service."""
    config = load_config()
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("MAPE-K Planner Service")
    logger.info("=" * 60)
    
    service = PlannerService(config)
    
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
