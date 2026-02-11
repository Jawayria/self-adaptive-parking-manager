"""
Parking Lot Simulator for Self-Adaptive Smart Parking Lot Manager

This module simulates parking lot operations including:
- Vehicle arrivals and departures
- Queue management
- Sensor data publishing via MQTT
- Responding to control commands from the autonomic manager
"""

import random
import logging
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

from .models import (
    GateState,
    SensorData,
    ControlCommand,
    AdaptationAction,
    ParkingLotConfig
)
from .mqtt_client import MQTTClient, ParkingMQTTTopics

logger = logging.getLogger(__name__)


class ParkingLotSimulator:
    """
    Simulates a parking lot with dynamic vehicle arrivals and departures.
    
    Features:
    - Realistic vehicle arrival/departure patterns
    - External traffic simulation
    - Queue management
    - Response to control commands
    - Sensor data publishing via MQTT
    """
    
    def __init__(
        self,
        config: ParkingLotConfig,
        mqtt_client: MQTTClient,
        simulation_params: Dict[str, Any]
    ):
        """
        Initialize the parking lot simulator.
        
        Args:
            config: Parking lot configuration
            mqtt_client: MQTT client for communication
            simulation_params: Simulation parameters from config
        """
        self.config = config
        self.mqtt_client = mqtt_client
        self.simulation_params = simulation_params
        
        # Initialize state
        self.current_occupancy = config.initial_occupancy
        self.current_price = config.base_price
        self.gate_state = GateState.OPEN
        self.queue_length = 0
        self.rejected_vehicles = 0
        self.total_revenue = 0.0
        self.redirect_target: Optional[str] = None
        
        # Simulation control
        self._running = False
        self._simulation_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Traffic simulation
        self._external_traffic_level = 0.5  # Default moderate traffic
        
        logger.info(f"Initialized parking lot simulator: {config.name} ({config.id})")
        logger.info(f"  Capacity: {config.total_capacity}, Initial occupancy: {config.initial_occupancy}")
    
    def _setup_mqtt_subscriptions(self):
        """Subscribe to control command topic"""
        control_topic = ParkingMQTTTopics.get_control_topic(self.config.id)
        self.mqtt_client.subscribe(control_topic, self._handle_control_command)
        logger.info(f"Subscribed to control topic: {control_topic}")
    
    def _handle_control_command(self, topic: str, payload: Dict[str, Any]):
        """
        Handle incoming control commands from the autonomic manager.
        
        Args:
            topic: MQTT topic
            payload: Command payload
        """
        try:
            command = ControlCommand.from_json(payload) if isinstance(payload, str) else ControlCommand(
                lot_id=payload.get("lot_id", self.config.id),
                action=AdaptationAction(payload["action"]),
                parameters=payload.get("parameters", {}),
                reason=payload.get("reason", "")
            )
            
            logger.info(f"Received control command: {command.action.value} - {command.reason}")
            
            with self._lock:
                self._execute_command(command)
                
        except Exception as e:
            logger.error(f"Error handling control command: {e}")
    
    def _execute_command(self, command: ControlCommand):
        """Execute a control command"""
        if command.action == AdaptationAction.INCREASE_PRICE:
            new_price = command.parameters.get("new_price", self.current_price * 1.1)
            self.current_price = min(new_price, self.config.max_price)
            logger.info(f"Price increased to ${self.current_price:.2f}")
            
        elif command.action == AdaptationAction.DECREASE_PRICE:
            new_price = command.parameters.get("new_price", self.current_price * 0.9)
            self.current_price = max(new_price, self.config.min_price)
            logger.info(f"Price decreased to ${self.current_price:.2f}")
            
        elif command.action == AdaptationAction.CLOSE_GATE:
            self.gate_state = GateState.CLOSED
            logger.info("Gate CLOSED")
            
        elif command.action == AdaptationAction.OPEN_GATE:
            self.gate_state = GateState.OPEN
            logger.info("Gate OPENED")
            
        elif command.action == AdaptationAction.REDIRECT_VEHICLES:
            self.redirect_target = command.parameters.get("target_lot")
            logger.info(f"Vehicles being redirected to: {self.redirect_target}")
    
    def _simulate_traffic_level(self) -> float:
        """
        Simulate external traffic level based on time of day.
        
        Returns:
            Traffic level from 0.0 to 1.0
        """
        if not self.simulation_params.get("traffic_variation", True):
            return 0.5
        
        current_hour = datetime.now().hour
        peak_hours = self.simulation_params.get("peak_hours", [8, 9, 12, 13, 17, 18])
        
        if current_hour in peak_hours:
            # Peak traffic
            base_level = 0.8
        elif current_hour in [7, 10, 11, 14, 15, 16, 19]:
            # Moderate traffic
            base_level = 0.5
        else:
            # Low traffic
            base_level = 0.2
        
        # Add some randomness
        return min(1.0, max(0.0, base_level + random.uniform(-0.1, 0.1)))
    
    def _calculate_arrival_probability(self) -> float:
        """
        Calculate probability of a vehicle arriving this tick.
        
        Factors:
        - Base arrival rate
        - External traffic level
        - Current price (higher price = lower demand)
        - Available capacity
        """
        base_rate = self.simulation_params.get("base_arrival_rate", 0.3)
        
        # Traffic multiplier
        traffic_multiplier = 0.5 + self._external_traffic_level
        
        # Price sensitivity (higher prices reduce arrivals)
        price_ratio = self.current_price / self.config.base_price
        price_multiplier = max(0.3, 1.5 - (0.5 * price_ratio))
        
        # Capacity factor (near-full lots naturally see fewer arrivals)
        occupancy_ratio = self.current_occupancy / self.config.total_capacity
        capacity_multiplier = 1.0 if occupancy_ratio < 0.9 else (1.0 - occupancy_ratio) * 5
        
        return base_rate * traffic_multiplier * price_multiplier * capacity_multiplier
    
    def _calculate_departure_probability(self) -> float:
        """
        Calculate probability of a vehicle departing this tick.
        
        Returns:
            Departure probability
        """
        if self.current_occupancy == 0:
            return 0.0
        
        base_rate = self.simulation_params.get("base_departure_rate", 0.15)
        
        # Higher prices encourage shorter stays
        price_ratio = self.current_price / self.config.base_price
        price_multiplier = 1.0 + (0.2 * (price_ratio - 1))
        
        return min(0.5, base_rate * price_multiplier)
    
    def _simulation_tick(self):
        """
        Execute one simulation tick.
        
        Updates:
        - External traffic level
        - Vehicle arrivals
        - Vehicle departures
        - Queue management
        - Sensor data publishing
        """
        with self._lock:
            # Update traffic level
            self._external_traffic_level = self._simulate_traffic_level()
            
            # Process arrivals
            arrival_prob = self._calculate_arrival_probability()
            # Increased from 5 to 20 to allow for realistic peak traffic scenarios
            arrivals = sum(1 for _ in range(10) if random.random() < arrival_prob)
            
            # Process departures
            departure_prob = self._calculate_departure_probability()
            departures = sum(1 for _ in range(self.current_occupancy) 
                           if random.random() < departure_prob)
            
            # Apply departures
            self.current_occupancy = max(0, self.current_occupancy - departures)
            
            # Apply arrivals (considering gate state and capacity)
            for _ in range(arrivals):
                if self.gate_state == GateState.CLOSED:
                    # Vehicle goes to queue or is rejected
                    if self.queue_length < 15:  # Max queue size
                        self.queue_length += 1
                    else:
                        self.rejected_vehicles += 1
                elif self.current_occupancy < self.config.total_capacity:
                    # Vehicle enters lot
                    self.current_occupancy += 1
                    self.total_revenue += self.current_price
                elif self.queue_length < 15:
                    # Lot full, vehicle joins queue
                    self.queue_length += 1
                else:
                    # Queue full, vehicle rejected
                    self.rejected_vehicles += 1
            
            # Process queue when there's space and gate is open
            while (self.queue_length > 0 and 
                   self.current_occupancy < self.config.total_capacity and
                   self.gate_state == GateState.OPEN):
                self.queue_length -= 1
                self.current_occupancy += 1
                self.total_revenue += self.current_price
            
            # Natural queue decay (people give up)
            if self.queue_length > 0 and random.random() < 0.1:
                gave_up = random.randint(0, min(2, self.queue_length))
                self.queue_length -= gave_up
                self.rejected_vehicles += gave_up
        
        # Publish sensor data
        self._publish_sensor_data()
    
    def _publish_sensor_data(self):
        """Publish current sensor data via MQTT"""
        occupancy_percentage = (self.current_occupancy / self.config.total_capacity) * 100
        
        sensor_data = SensorData(
            lot_id=self.config.id,
            occupancy_percentage=occupancy_percentage,
            current_occupancy=self.current_occupancy,
            total_capacity=self.config.total_capacity,
            queue_length=self.queue_length,
            rejected_count=self.rejected_vehicles,
            current_price=self.current_price,
            gate_state=self.gate_state.value,
            revenue=self.total_revenue,
            external_traffic_level=self._external_traffic_level,
            timestamp=datetime.now()
        )
        
        topic = ParkingMQTTTopics.get_sensor_topic(self.config.id)
        self.mqtt_client.publish(topic, sensor_data.to_dict())
        
        logger.debug(
            f"[{self.config.id}] Occupancy: {occupancy_percentage:.1f}% "
            f"({self.current_occupancy}/{self.config.total_capacity}), "
            f"Queue: {self.queue_length}, Price: ${self.current_price:.2f}, "
            f"Revenue: ${self.total_revenue:.2f}"
        )
    
    def _simulation_loop(self):
        """Main simulation loop running in a separate thread"""
        tick_interval = self.simulation_params.get("tick_interval_seconds", 2)
        
        logger.info(f"Starting simulation loop for {self.config.id} (interval: {tick_interval}s)")
        
        while self._running:
            try:
                self._simulation_tick()
                time.sleep(tick_interval)
            except Exception as e:
                logger.error(f"Error in simulation tick: {e}")
                time.sleep(1)
        
        logger.info(f"Simulation loop stopped for {self.config.id}")
    
    def start(self):
        """Start the parking lot simulation"""
        if self._running:
            logger.warning(f"Simulator for {self.config.id} is already running")
            return
        
        self._setup_mqtt_subscriptions()
        self._running = True
        self._simulation_thread = threading.Thread(
            target=self._simulation_loop,
            name=f"ParkingSimulator-{self.config.id}",
            daemon=True
        )
        self._simulation_thread.start()
        
        logger.info(f"Started parking lot simulator: {self.config.id}")
    
    def stop(self):
        """Stop the parking lot simulation"""
        self._running = False
        if self._simulation_thread:
            self._simulation_thread.join(timeout=5)
        logger.info(f"Stopped parking lot simulator: {self.config.id}")
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state as a dictionary"""
        with self._lock:
            return {
                "lot_id": self.config.id,
                "name": self.config.name,
                "current_occupancy": self.current_occupancy,
                "total_capacity": self.config.total_capacity,
                "occupancy_percentage": (self.current_occupancy / self.config.total_capacity) * 100,
                "queue_length": self.queue_length,
                "rejected_vehicles": self.rejected_vehicles,
                "current_price": self.current_price,
                "gate_state": self.gate_state.value,
                "total_revenue": self.total_revenue,
                "external_traffic_level": self._external_traffic_level
            }


class ParkingSystemSimulator:
    """
    Manages multiple parking lot simulators as a unified system.
    """
    
    def __init__(
        self,
        lot_configs: List[ParkingLotConfig],
        mqtt_client: MQTTClient,
        simulation_params: Dict[str, Any]
    ):
        """
        Initialize the parking system simulator.
        
        Args:
            lot_configs: List of parking lot configurations
            mqtt_client: Shared MQTT client
            simulation_params: Simulation parameters
        """
        self.mqtt_client = mqtt_client
        self.simulators: Dict[str, ParkingLotSimulator] = {}
        
        for config in lot_configs:
            self.simulators[config.id] = ParkingLotSimulator(
                config=config,
                mqtt_client=mqtt_client,
                simulation_params=simulation_params
            )
        
        logger.info(f"Initialized parking system with {len(self.simulators)} lots")
    
    def start_all(self):
        """Start all parking lot simulators"""
        for simulator in self.simulators.values():
            simulator.start()
        logger.info("All parking lot simulators started")
    
    def stop_all(self):
        """Stop all parking lot simulators"""
        for simulator in self.simulators.values():
            simulator.stop()
        logger.info("All parking lot simulators stopped")
    
    def get_simulator(self, lot_id: str) -> Optional[ParkingLotSimulator]:
        """Get a specific parking lot simulator"""
        return self.simulators.get(lot_id)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state snapshots for all lots"""
        return {
            lot_id: sim.get_state_snapshot()
            for lot_id, sim in self.simulators.items()
        }
