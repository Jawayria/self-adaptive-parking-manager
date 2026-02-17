"""
Autonomic Manager implementing MAPE-K Loop for Smart Parking Lot Management

This module contains the core autonomic manager that implements:
- Monitor: Collects real-time parking data from sensors via MQTT
- Analyze: Detects congestion, under-utilization, and deviations from goals
- Plan: Selects adaptation actions (price adjustment, gate control)
- Execute: Applies adaptations by issuing MQTT control commands
- Knowledge: Stores configuration, historical data, and decision rules
"""

import logging
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
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
        sensor_topic = ParkingMQTTTopics.get_all_sensors_topic()
        self.mqtt_client.subscribe(sensor_topic, self._on_sensor_data)
        logger.info(f"Monitor: Subscribed to {sensor_topic}")

    def _on_sensor_data(self, topic: str, payload: Dict[str, Any]):
        """Monitor callback: Process incoming sensor data."""
        try:
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)

            sensor_data = SensorData(
                lot_id=payload["lot_id"],
                occupancy_percentage=payload["occupancy_percentage"],
                current_occupancy=payload["current_occupancy"],
                total_capacity=payload["total_capacity"],
                queue_length=payload.get("queue_length", 0),  # ignored in logic
                rejected_count=payload["rejected_count"],
                current_price=payload["current_price"],
                gate_state=payload["gate_state"],
                revenue=payload["revenue"],
                external_traffic_level=payload.get("external_traffic_level", 0.5),
                timestamp=datetime.fromisoformat(payload["timestamp"]) if "timestamp" in payload else datetime.now()
            )

            self.knowledge.store_sensor_data(sensor_data)

            logger.info(
                f"Monitor: Stored data from {sensor_data.lot_id} - "
                f"Occupancy: {sensor_data.occupancy_percentage:.1f}%"
            )

        except Exception as e:
            logger.error(f"Monitor: Error processing sensor data: {e}", exc_info=True)

    # =========================================================================
    # ANALYZE Component
    # =========================================================================

    def _analyze(self, lot_id: str) -> Optional[AnalysisResult]:
        """
        Analyze current state and recommend actions.

        Gate policy (NO queue logic):
        - Close gate when occupancy >= gate_close_occupancy_threshold
        - Open gate when occupancy < gate_reopen_occupancy
        """
        current_state = self.knowledge.get_current_state(lot_id)
        if not current_state:
            return None

        lot_config = self.knowledge.get_lot_config(lot_id)
        if not lot_config:
            return None

        thresholds = self.knowledge.get_adaptation_thresholds()

        issues: List[str] = []
        recommended_actions: List[AdaptationAction] = []
        severity = "low"
        confidence = 0.7

        occupancy_pct = current_state.occupancy_percentage / 100.0  # 0..1

        # Thresholds
        critical_occ = thresholds.get("critical_occupancy_threshold", 0.98)
        high_occ = thresholds.get("high_occupancy_threshold", 0.85)
        low_occ = thresholds.get("low_occupancy_threshold", 0.50)

        gate_close_occ = thresholds.get("gate_close_occupancy_threshold", high_occ)
        gate_reopen_occ = thresholds.get("gate_reopen_occupancy", 0.80)

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
        if occupancy_pct >= gate_close_occ and current_state.gate_state == "open":
            issues.append(
                f"Gate close policy: occupancy {occupancy_pct*100:.1f}% >= {gate_close_occ*100:.1f}%"
            )
            if AdaptationAction.CLOSE_GATE not in recommended_actions:
                recommended_actions.append(AdaptationAction.CLOSE_GATE)
            if severity != "critical":
                severity = "high"
            confidence = min(confidence + 0.1, 1.0)

        if occupancy_pct < gate_reopen_occ and current_state.gate_state == "closed":
            issues.append(
                f"Gate reopen policy: occupancy {occupancy_pct*100:.1f}% < {gate_reopen_occ*100:.1f}%"
            )
            if AdaptationAction.OPEN_GATE not in recommended_actions:
                recommended_actions.append(AdaptationAction.OPEN_GATE)

        # -------------------------
        # Price bounds enforcement
        # -------------------------
        if (current_state.current_price >= lot_config.max_price and
                AdaptationAction.INCREASE_PRICE in recommended_actions):
            recommended_actions.remove(AdaptationAction.INCREASE_PRICE)
            issues.append("Price at maximum - cannot increase further")

        if (current_state.current_price <= lot_config.min_price and
                AdaptationAction.DECREASE_PRICE in recommended_actions):
            recommended_actions.remove(AdaptationAction.DECREASE_PRICE)
            issues.append("Price at minimum - cannot decrease further")

        if not issues or not recommended_actions and len(issues) == 0:
            return None

        return AnalysisResult(
            lot_id=lot_id,
            issues_detected=issues,
            severity=severity,
            current_state={
                "occupancy_percentage": current_state.occupancy_percentage,
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
        """Create a concrete adaptation plan from analysis results."""
        if not analysis.recommended_actions:
            return None

        # Cooldown
        last_adaptation = self._last_adaptations.get(analysis.lot_id)
        if last_adaptation:
            elapsed = (datetime.now() - last_adaptation).total_seconds()
            if elapsed < self._adaptation_cooldown:
                logger.debug(f"Plan: Skipping adaptation for {analysis.lot_id} - cooldown active")
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
            expected_outcome=self._predict_outcome(analysis, final_actions),
            confidence=analysis.confidence
        )

        logger.info(f"Plan: Created adaptation decision for {analysis.lot_id}")
        logger.info(f"  Issues: {analysis.issues_detected}")
        logger.info(f"  Actions: {[a.value for a in final_actions]}")
        logger.info(f"  Expected outcome: {decision.expected_outcome}")

        return decision

    def _predict_outcome(self, analysis: AnalysisResult, actions: List[AdaptationAction]) -> str:
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

    # =========================================================================
    # EXECUTE Component
    # =========================================================================

    def _execute(self, decision: AdaptationDecision):
        """Execute planned adaptations by sending MQTT control commands."""
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
                self.mqtt_client.publish(control_topic, command.to_dict())
                logger.info(f"Execute: Sent {action.value} command to {decision.lot_id}")

        self._last_adaptations[decision.lot_id] = datetime.now()
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
        """Create a control command for an action."""
        parameters: Dict[str, Any] = {}

        if action == AdaptationAction.INCREASE_PRICE:
            step = thresholds.get("price_increase_step", 1.0)
            if current_state and current_state.occupancy_percentage >= 98:
                step *= thresholds.get("critical_price_multiplier", 1.5)

            new_price = min(
                (current_state.current_price + step) if current_state else (config.base_price + step),
                config.max_price
            )
            parameters["new_price"] = round(new_price, 2)

        elif action == AdaptationAction.DECREASE_PRICE:
            step = thresholds.get("price_decrease_step", 0.5)
            new_price = max(
                (current_state.current_price - step) if current_state else (config.base_price - step),
                config.min_price
            )
            parameters["new_price"] = round(new_price, 2)

        

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
        """Execute one complete MAPE-K cycle for all managed parking lots."""
        all_states = self.knowledge.get_all_current_states()
        if not all_states:
            logger.debug("MAPE-K: No lot states available yet")
            return

        self._update_system_metrics(all_states)

        for lot_id in all_states.keys():
            try:
                analysis = self._analyze(lot_id)
                if analysis:
                    logger.info(f"MAPE-K [{lot_id}]: Analysis detected {len(analysis.issues_detected)} issues")
                    decision = self._plan(analysis)
                    if decision:
                        self._execute(decision)
            except Exception as e:
                logger.error(f"MAPE-K error for {lot_id}: {e}", exc_info=True)

    def _update_system_metrics(self, all_states: Dict[str, SensorData]):
        """Calculate and store system-wide metrics."""
        thresholds = self.knowledge.get_adaptation_thresholds()

        total_revenue = sum(s.revenue for s in all_states.values())
        total_occupancy = sum(s.current_occupancy for s in all_states.values())
        total_capacity = sum(s.total_capacity for s in all_states.values())
        total_rejected = sum(s.rejected_count for s in all_states.values())
        total_queue = sum(getattr(s, "queue_length", 0) for s in all_states.values())  # ignored in logic
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

        self.knowledge.store_system_metrics(metrics)

        self.mqtt_client.publish(
            ParkingMQTTTopics.SYSTEM_METRICS,
            metrics.to_dict()
        )

    def _control_loop(self):
        """Main MAPE-K control loop running in a separate thread."""
        logger.info("MAPE-K control loop started")

        while self._running:
            try:
                self._mape_k_cycle()
                time.sleep(self._loop_interval)
            except Exception as e:
                logger.error(f"MAPE-K cycle error: {e}", exc_info=True)
                time.sleep(1)

        logger.info("MAPE-K control loop stopped")

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def start(self):
        """Start the autonomic manager."""
        if self._running:
            logger.warning("Autonomic Manager is already running")
            return

        self._setup_monitoring()

        self._running = True
        self._loop_thread = threading.Thread(
            target=self._control_loop,
            name="MAPE-K-ControlLoop",
            daemon=True
        )
        self._loop_thread.start()

        logger.info("Autonomic Manager started")

    def stop(self):
        """Stop the autonomic manager."""
        self._running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=5)
        logger.info("Autonomic Manager stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current manager status."""
        return {
            "running": self._running,
            "managed_lots": list(self.knowledge.get_all_current_states().keys()),
            "loop_interval": self._loop_interval,
            "adaptation_cooldown": self._adaptation_cooldown,
            "last_adaptations": {k: v.isoformat() for k, v in self._last_adaptations.items()}
        }
