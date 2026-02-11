"""
Data Models for Self-Adaptive Smart Parking Lot Manager

This module contains all data structures used throughout the system.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import json


class GateState(Enum):
    """Enumeration for gate states"""
    OPEN = "open"
    CLOSED = "closed"


class AdaptationAction(Enum):
    """Types of adaptation actions the system can take"""
    INCREASE_PRICE = "increase_price"
    DECREASE_PRICE = "decrease_price"
    CLOSE_GATE = "close_gate"
    OPEN_GATE = "open_gate"
    REDIRECT_VEHICLES = "redirect_vehicles"
    NO_ACTION = "no_action"


@dataclass
class ParkingLotState:
    """Represents the current state of a parking lot"""
    lot_id: str
    total_capacity: int
    current_occupancy: int
    queue_length: int
    rejected_vehicles: int
    current_price: float
    gate_state: GateState
    revenue: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def occupancy_percentage(self) -> float:
        """Calculate occupancy as a percentage"""
        if self.total_capacity == 0:
            return 0.0
        return self.current_occupancy / self.total_capacity
    
    @property
    def available_spaces(self) -> int:
        """Calculate available parking spaces"""
        return max(0, self.total_capacity - self.current_occupancy)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "lot_id": self.lot_id,
            "total_capacity": self.total_capacity,
            "current_occupancy": self.current_occupancy,
            "occupancy_percentage": round(self.occupancy_percentage * 100, 2),
            "available_spaces": self.available_spaces,
            "queue_length": self.queue_length,
            "rejected_vehicles": self.rejected_vehicles,
            "current_price": self.current_price,
            "gate_state": self.gate_state.value,
            "revenue": round(self.revenue, 2),
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParkingLotState':
        """Create ParkingLotState from dictionary"""
        return cls(
            lot_id=data["lot_id"],
            total_capacity=data["total_capacity"],
            current_occupancy=data["current_occupancy"],
            queue_length=data["queue_length"],
            rejected_vehicles=data["rejected_vehicles"],
            current_price=data["current_price"],
            gate_state=GateState(data["gate_state"]),
            revenue=data["revenue"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now()
        )


@dataclass
class SensorData:
    """Data published by parking lot sensors"""
    lot_id: str
    occupancy_percentage: float
    current_occupancy: int
    total_capacity: int
    queue_length: int
    rejected_count: int
    current_price: float
    gate_state: str
    revenue: float
    external_traffic_level: float  # 0.0 to 1.0, represents traffic intensity
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "lot_id": self.lot_id,
            "occupancy_percentage": round(self.occupancy_percentage, 2),
            "current_occupancy": self.current_occupancy,
            "total_capacity": self.total_capacity,
            "queue_length": self.queue_length,
            "rejected_count": self.rejected_count,
            "current_price": self.current_price,
            "gate_state": self.gate_state,
            "revenue": round(self.revenue, 2),
            "external_traffic_level": round(self.external_traffic_level, 2),
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SensorData':
        """Create SensorData from JSON string"""
        data = json.loads(json_str)
        return cls(
            lot_id=data["lot_id"],
            occupancy_percentage=data["occupancy_percentage"],
            current_occupancy=data["current_occupancy"],
            total_capacity=data["total_capacity"],
            queue_length=data["queue_length"],
            rejected_count=data["rejected_count"],
            current_price=data["current_price"],
            gate_state=data["gate_state"],
            revenue=data["revenue"],
            external_traffic_level=data.get("external_traffic_level", 0.5),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now()
        )


@dataclass
class ControlCommand:
    """Commands sent to parking lot effectors"""
    lot_id: str
    action: AdaptationAction
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "lot_id": self.lot_id,
            "action": self.action.value,
            "parameters": self.parameters,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ControlCommand':
        """Create ControlCommand from JSON string"""
        data = json.loads(json_str)
        return cls(
            lot_id=data["lot_id"],
            action=AdaptationAction(data["action"]),
            parameters=data.get("parameters", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            reason=data.get("reason", "")
        )


@dataclass
class AdaptationDecision:
    """Represents a decision made by the autonomic manager"""
    lot_id: str
    timestamp: datetime
    trigger_condition: str
    current_state: Dict[str, Any]
    actions: List[AdaptationAction]
    expected_outcome: str
    confidence: float  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "lot_id": self.lot_id,
            "timestamp": self.timestamp.isoformat(),
            "trigger_condition": self.trigger_condition,
            "current_state": self.current_state,
            "actions": [a.value for a in self.actions],
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence
        }


@dataclass
class SystemMetrics:
    """Aggregated system metrics for analysis"""
    timestamp: datetime
    total_revenue: float
    total_occupancy: int
    total_capacity: int
    total_rejected: int
    total_queue_length: int
    average_price: float
    lots_at_capacity: int
    lots_under_utilized: int
    
    @property
    def overall_utilization(self) -> float:
        """Calculate overall system utilization"""
        if self.total_capacity == 0:
            return 0.0
        return self.total_occupancy / self.total_capacity
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_revenue": round(self.total_revenue, 2),
            "total_occupancy": self.total_occupancy,
            "total_capacity": self.total_capacity,
            "overall_utilization": round(self.overall_utilization * 100, 2),
            "total_rejected": self.total_rejected,
            "total_queue_length": self.total_queue_length,
            "average_price": round(self.average_price, 2),
            "lots_at_capacity": self.lots_at_capacity,
            "lots_under_utilized": self.lots_under_utilized
        }


@dataclass
class ParkingLotConfig:
    """Configuration for a single parking lot"""
    id: str
    name: str
    total_capacity: int
    initial_occupancy: int
    base_price: float
    min_price: float
    max_price: float
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParkingLotConfig':
        """Create from dictionary"""
        return cls(
            id=data["id"],
            name=data["name"],
            total_capacity=data["total_capacity"],
            initial_occupancy=data.get("initial_occupancy", 0),
            base_price=data["base_price"],
            min_price=data["min_price"],
            max_price=data["max_price"]
        )
