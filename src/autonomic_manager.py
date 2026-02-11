"""
Autonomic Manager implementing MAPE-K Loop for Smart Parking Lot Management

This module contains the core autonomic manager that implements:
- Monitor: Collects real-time parking data from sensors via MQTT
- Analyze: Detects congestion, under-utilization, and deviations from goals
- Plan: Selects adaptation actions (price adjustment, gate control, redirection)
- Execute: Applies adaptations by issuing MQTT control commands
- Knowledge: Stores configuration, historical data, and decision rules
"""

import logging
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .models import (
    SensorData,
    ControlCommand,
    AdaptationAction,
    AdaptationDecision,
    SystemMetrics,
    ParkingLotConfig
)
from .mqtt_client import MQTTClient, ParkingMQTTTopics
from .knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of the analysis phase"""
    lot_id: str
    issues_detected: List[str]
    severity: str  # "low", "medium", "high", "critical"
    current_state: Dict[str, Any]
    recommended_actions: List[AdaptationAction]
    confidence: float


class MAPEKAutonomicManager:
    """
    Centralized Autonomic Manager implementing the MAPE-K control loop.
    
    This manager monitors one or more parking lots and autonomously adapts
    system behavior to maintain optimal operations.
    
    MAPE-K Components:
    - Monitor: Subscribes to MQTT sensor data from all parking lots
    - Analyze: Evaluates current state against goals and thresholds
    - Plan: Determines appropriate adaptation actions
    - Execute: Sends control commands via MQTT
    - Knowledge: Stores state, history, and rules in InfluxDB
    """
    
    def __init__(
        self,
        mqtt_client: MQTTClient,
        knowledge_base: KnowledgeBase,
        lot_configs: List[ParkingLotConfig],
        adaptation_config: Dict[str, Any]
    ):
        """
        Initialize the Autonomic Manager.
        
        Args:
            mqtt_client: MQTT client for communication
            knowledge_base: Knowledge base for storing data
            lot_configs: Configuration for managed parking lots
            adaptation_config: Adaptation thresholds and parameters
        """
        self.mqtt_client = mqtt_client
        self.knowledge = knowledge_base
        self.adaptation_config = adaptation_config
        
        # Store lot configurations in knowledge base
        for config in lot_configs:
            self.knowledge.set_lot_config(config)
        
        # Store adaptation thresholds
        self.knowledge.set_adaptation_thresholds(adaptation_config)
        
        # MAPE-K loop control
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_interval = 3  # seconds between MAPE-K cycles
        
        # Cooldown to prevent rapid oscillations
        self._last_adaptations: Dict[str, datetime] = {}
        self._adaptation_cooldown = 10  # seconds
        
        logger.info("Autonomic Manager initialized")
        logger.info(f"Managing {len(lot_configs)} parking lots")
        logger.info(f"Adaptation thresholds: {adaptation_config}")
    
    # =========================================================================
    # MONITOR Component
    # =========================================================================
    
    def _setup_monitoring(self):
        """Set up MQTT subscriptions for monitoring all parking lots"""
        # Subscribe to all sensor data
        sensor_topic = ParkingMQTTTopics.get_all_sensors_topic()
        self.mqtt_client.subscribe(sensor_topic, self._on_sensor_data)
        logger.info(f"Monitor: Subscribed to {sensor_topic}")
    
    def _on_sensor_data(self, topic: str, payload: Dict[str, Any]):
        """
        Monitor callback: Process incoming sensor data.
        
        This is the entry point of the MONITOR phase.
        """
        try:
            # Parse sensor data
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            
            sensor_data = SensorData(
                lot_id=payload["lot_id"],
                occupancy_percentage=payload["occupancy_percentage"],
                current_occupancy=payload["current_occupancy"],
                total_capacity=payload["total_capacity"],
                queue_length=payload["queue_length"],
                rejected_count=payload["rejected_count"],
                current_price=payload["current_price"],
                gate_state=payload["gate_state"],
                revenue=payload["revenue"],
                external_traffic_level=payload.get("external_traffic_level", 0.5),
                timestamp=datetime.fromisoformat(payload["timestamp"]) if "timestamp" in payload else datetime.now()
            )
            
            # Store in knowledge base
            self.knowledge.store_sensor_data(sensor_data)
            
            logger.info(f"Monitor: Stored data from {sensor_data.lot_id} - "
                        f"Occupancy: {sensor_data.occupancy_percentage:.1f}%")
            
        except Exception as e:
            logger.error(f"Monitor: Error processing sensor data: {e}", exc_info=True)
    
    # =========================================================================
    # ANALYZE Component
    # =========================================================================
    
    def _analyze(self, lot_id: str) -> Optional[AnalysisResult]:
        """
        Analyze component: Evaluate current state against goals.
        
        Detects:
        - High occupancy (potential congestion)
        - Low occupancy (under-utilization)
        - Long queues
        - High rejection rates
        - Price optimization opportunities
        
        Args:
            lot_id: Parking lot to analyze
            
        Returns:
            AnalysisResult or None if no issues detected
        """
        current_state = self.knowledge.get_current_state(lot_id)
        if not current_state:
            return None
        
        lot_config = self.knowledge.get_lot_config(lot_id)
        if not lot_config:
            return None
        
        thresholds = self.knowledge.get_adaptation_thresholds()
        
        issues = []
        recommended_actions = []
        severity = "low"
        confidence = 0.7
        
        occupancy_pct = current_state.occupancy_percentage / 100.0  # Convert to 0-1
        
        # Check for critical occupancy
        if occupancy_pct >= thresholds.get("critical_occupancy_threshold", 0.98):
            issues.append("CRITICAL: Parking lot at capacity")
            severity = "critical"
            recommended_actions.append(AdaptationAction.INCREASE_PRICE)
            # Close gate at critical occupancy to manage inflow
            if current_state.gate_state == "open":
                recommended_actions.append(AdaptationAction.CLOSE_GATE)
            if current_state.queue_length > 0:
                recommended_actions.append(AdaptationAction.REDIRECT_VEHICLES)
            confidence = 0.95
        
        # Check for high occupancy
        elif occupancy_pct >= thresholds.get("high_occupancy_threshold", 0.90):
            issues.append(f"High occupancy: {occupancy_pct*100:.1f}%")
            severity = "high"
            recommended_actions.append(AdaptationAction.INCREASE_PRICE)
            confidence = 0.85
        
        # Check for low occupancy
        elif occupancy_pct <= thresholds.get("low_occupancy_threshold", 0.50):
            issues.append(f"Low occupancy: {occupancy_pct*100:.1f}%")
            severity = "medium"
            recommended_actions.append(AdaptationAction.DECREASE_PRICE)
            confidence = 0.8
        
        # Check queue length
        queue_threshold = thresholds.get("gate_close_queue_threshold", 8)
        if current_state.queue_length >= queue_threshold:
            issues.append(f"Long queue: {current_state.queue_length} vehicles")
            if severity != "critical":
                severity = "high"
            if current_state.gate_state == "open":
                recommended_actions.append(AdaptationAction.CLOSE_GATE)
            confidence = min(confidence + 0.1, 1.0)
        
        # Check if gate should be reopened (independent of queue check)
        # Gate reopens when occupancy drops AND queue is manageable
        reopen_occupancy = thresholds.get("gate_reopen_occupancy", 0.85)
        if (current_state.gate_state == "closed" and 
            occupancy_pct < reopen_occupancy and
            current_state.queue_length < queue_threshold):
            issues.append(f"Gate closed but lot has capacity (occ: {occupancy_pct*100:.0f}%, queue: {current_state.queue_length})")
            recommended_actions.append(AdaptationAction.OPEN_GATE)
        
        # Check price bounds
        if current_state.current_price >= lot_config.max_price and AdaptationAction.INCREASE_PRICE in recommended_actions:
            recommended_actions.remove(AdaptationAction.INCREASE_PRICE)
            issues.append("Price at maximum - cannot increase further")
        
        if current_state.current_price <= lot_config.min_price and AdaptationAction.DECREASE_PRICE in recommended_actions:
            recommended_actions.remove(AdaptationAction.DECREASE_PRICE)
            issues.append("Price at minimum - cannot decrease further")
        
        if not issues:
            return None
        
        return AnalysisResult(
            lot_id=lot_id,
            issues_detected=issues,
            severity=severity,
            current_state={
                "occupancy_percentage": current_state.occupancy_percentage,
                "queue_length": current_state.queue_length,
                "current_price": current_state.current_price,
                "gate_state": current_state.gate_state,
                "rejected_count": current_state.rejected_count,
                "revenue": current_state.revenue
            },
            recommended_actions=recommended_actions,
            confidence=confidence
        )
    
    # =========================================================================
    # PLAN Component
    # =========================================================================
    
    def _plan(self, analysis: AnalysisResult) -> Optional[AdaptationDecision]:
        """
        Plan component: Determine specific adaptation actions.
        
        Takes the analysis result and creates a concrete plan with
        specific parameters for each action.
        
        Args:
            analysis: Result from the analyze phase
            
        Returns:
            AdaptationDecision with specific actions and parameters
        """
        if not analysis.recommended_actions:
            return None
        
        lot_config = self.knowledge.get_lot_config(analysis.lot_id)
        thresholds = self.knowledge.get_adaptation_thresholds()
        
        # Check cooldown
        last_adaptation = self._last_adaptations.get(analysis.lot_id)
        if last_adaptation:
            elapsed = (datetime.now() - last_adaptation).total_seconds()
            if elapsed < self._adaptation_cooldown:
                logger.debug(f"Plan: Skipping adaptation for {analysis.lot_id} - cooldown active")
                return None
        
        # Filter and prioritize actions
        final_actions = []
        for action in analysis.recommended_actions:
            # Avoid conflicting actions
            if action == AdaptationAction.OPEN_GATE and AdaptationAction.CLOSE_GATE in final_actions:
                continue
            if action == AdaptationAction.CLOSE_GATE and AdaptationAction.OPEN_GATE in final_actions:
                continue
            final_actions.append(action)
        
        if not final_actions:
            return None
        
        # Create decision
        decision = AdaptationDecision(
            lot_id=analysis.lot_id,
            timestamp=datetime.now(),
            trigger_condition="; ".join(analysis.issues_detected),
            current_state=analysis.current_state,
            actions=final_actions,
            expected_outcome=self._predict_outcome(analysis, final_actions),
            confidence=analysis.confidence
        )
        
        logger.info(f"Plan: Created adaptation decision for {analysis.lot_id}")
        logger.info(f"  Issues: {analysis.issues_detected}")
        logger.info(f"  Actions: {[a.value for a in final_actions]}")
        logger.info(f"  Expected outcome: {decision.expected_outcome}")
        
        return decision
    
    def _predict_outcome(self, analysis: AnalysisResult, actions: List[AdaptationAction]) -> str:
        """Predict the expected outcome of the planned actions"""
        outcomes = []
        
        for action in actions:
            if action == AdaptationAction.INCREASE_PRICE:
                outcomes.append("reduced arrival rate, increased revenue per vehicle")
            elif action == AdaptationAction.DECREASE_PRICE:
                outcomes.append("increased arrival rate, improved utilization")
            elif action == AdaptationAction.CLOSE_GATE:
                outcomes.append("controlled inflow, queue management")
            elif action == AdaptationAction.OPEN_GATE:
                outcomes.append("resumed normal operations")
            elif action == AdaptationAction.REDIRECT_VEHICLES:
                outcomes.append("overflow management, reduced rejections")
        
        return "; ".join(outcomes)
    
    # =========================================================================
    # EXECUTE Component
    # =========================================================================
    
    def _execute(self, decision: AdaptationDecision):
        """
        Execute component: Apply the planned adaptations.
        
        Sends control commands via MQTT to the parking lot effectors.
        
        Args:
            decision: The adaptation decision to execute
        """
        lot_config = self.knowledge.get_lot_config(decision.lot_id)
        thresholds = self.knowledge.get_adaptation_thresholds()
        current_state = self.knowledge.get_current_state(decision.lot_id)
        
        control_topic = ParkingMQTTTopics.get_control_topic(decision.lot_id)
        
        for action in decision.actions:
            command = self._create_command(
                action, 
                decision.lot_id, 
                lot_config, 
                thresholds,
                current_state,
                decision.trigger_condition
            )
            
            if command:
                # Publish command via MQTT
                self.mqtt_client.publish(control_topic, command.to_dict())
                logger.info(f"Execute: Sent {action.value} command to {decision.lot_id}")
        
        # Update cooldown
        self._last_adaptations[decision.lot_id] = datetime.now()
        
        # Store decision in knowledge base
        self.knowledge.store_adaptation_decision(decision)
    
    def _create_command(
        self,
        action: AdaptationAction,
        lot_id: str,
        config: ParkingLotConfig,
        thresholds: Dict[str, Any],
        current_state: SensorData,
        reason: str
    ) -> Optional[ControlCommand]:
        """Create a control command for an action"""
        
        parameters = {}
        
        if action == AdaptationAction.INCREASE_PRICE:
            step = thresholds.get("price_increase_step", 1.0)
            # Use critical multiplier if at critical occupancy
            if current_state and current_state.occupancy_percentage >= 98:
                step *= thresholds.get("critical_price_multiplier", 1.5)
            new_price = min(
                current_state.current_price + step if current_state else config.base_price + step,
                config.max_price
            )
            parameters["new_price"] = round(new_price, 2)
            
        elif action == AdaptationAction.DECREASE_PRICE:
            step = thresholds.get("price_decrease_step", 0.5)
            new_price = max(
                current_state.current_price - step if current_state else config.base_price - step,
                config.min_price
            )
            parameters["new_price"] = round(new_price, 2)
            
        elif action == AdaptationAction.REDIRECT_VEHICLES:
            # Find alternative lot with capacity
            all_states = self.knowledge.get_all_current_states()
            for other_id, other_state in all_states.items():
                if other_id != lot_id:
                    other_occupancy = other_state.occupancy_percentage / 100.0
                    if other_occupancy < 0.85:
                        parameters["target_lot"] = other_id
                        break
        
        return ControlCommand(
            lot_id=lot_id,
            action=action,
            parameters=parameters,
            timestamp=datetime.now(),
            reason=reason
        )
    
    # =========================================================================
    # MAPE-K Control Loop
    # =========================================================================
    
    def _mape_k_cycle(self):
        """
        Execute one complete MAPE-K cycle for all managed parking lots.
        """
        all_states = self.knowledge.get_all_current_states()
        
        if not all_states:
            logger.debug("MAPE-K: No lot states available yet")
            return
        
        # Calculate and store system-wide metrics
        self._update_system_metrics(all_states)
        
        # Run MAPE-K for each lot
        for lot_id in all_states.keys():
            try:
                # ANALYZE
                analysis = self._analyze(lot_id)
                
                if analysis:
                    logger.info(f"MAPE-K [{lot_id}]: Analysis detected {len(analysis.issues_detected)} issues")
                    
                    # PLAN
                    decision = self._plan(analysis)
                    
                    if decision:
                        # EXECUTE
                        self._execute(decision)
                
            except Exception as e:
                logger.error(f"MAPE-K error for {lot_id}: {e}")
    
    def _update_system_metrics(self, all_states: Dict[str, SensorData]):
        """Calculate and store system-wide metrics"""
        thresholds = self.knowledge.get_adaptation_thresholds()
        
        total_revenue = sum(s.revenue for s in all_states.values())
        total_occupancy = sum(s.current_occupancy for s in all_states.values())
        total_capacity = sum(s.total_capacity for s in all_states.values())
        total_rejected = sum(s.rejected_count for s in all_states.values())
        total_queue = sum(s.queue_length for s in all_states.values())
        avg_price = sum(s.current_price for s in all_states.values()) / len(all_states)
        
        lots_at_capacity = sum(
            1 for s in all_states.values() 
            if s.occupancy_percentage >= 95
        )
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
        
        self.knowledge.store_system_metrics(metrics)
        
        # Publish to MQTT for real-time dashboards
        self.mqtt_client.publish(
            ParkingMQTTTopics.SYSTEM_METRICS,
            metrics.to_dict()
        )
    
    def _control_loop(self):
        """Main MAPE-K control loop running in a separate thread"""
        logger.info("MAPE-K control loop started")
        
        while self._running:
            try:
                self._mape_k_cycle()
                time.sleep(self._loop_interval)
            except Exception as e:
                logger.error(f"MAPE-K cycle error: {e}")
                time.sleep(1)
        
        logger.info("MAPE-K control loop stopped")
    
    # =========================================================================
    # Lifecycle Management
    # =========================================================================
    
    def start(self):
        """Start the autonomic manager"""
        if self._running:
            logger.warning("Autonomic Manager is already running")
            return
        
        # Set up MQTT monitoring
        self._setup_monitoring()
        
        # Start MAPE-K loop
        self._running = True
        self._loop_thread = threading.Thread(
            target=self._control_loop,
            name="MAPE-K-ControlLoop",
            daemon=True
        )
        self._loop_thread.start()
        
        logger.info("Autonomic Manager started")
    
    def stop(self):
        """Stop the autonomic manager"""
        self._running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=5)
        logger.info("Autonomic Manager stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current manager status"""
        return {
            "running": self._running,
            "managed_lots": list(self.knowledge.get_all_current_states().keys()),
            "loop_interval": self._loop_interval,
            "adaptation_cooldown": self._adaptation_cooldown,
            "last_adaptations": {
                k: v.isoformat() for k, v in self._last_adaptations.items()
            }
        }
