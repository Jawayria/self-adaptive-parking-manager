"""
Knowledge Base Component for Self-Adaptive Smart Parking Lot Manager

This module implements the Knowledge component of the MAPE-K loop using InfluxDB
for storing historical data, current state, and adaptation decisions.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from .models import (
    SensorData, 
    AdaptationDecision, 
    SystemMetrics,
    ParkingLotConfig
)

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Knowledge Base for the autonomic parking manager.
    
    Stores and retrieves:
    - Historical sensor data
    - Adaptation decisions and their outcomes
    - Configuration parameters
    - Decision rules and thresholds
    """
    
    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "my-super-secret-token",
        org: str = "parking-org",
        bucket: str = "parking_data"
    ):
        """
        Initialize the Knowledge Base with InfluxDB connection.
        
        Args:
            url: InfluxDB server URL
            token: Authentication token
            org: Organization name
            bucket: Bucket name for storing data
        """
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        
        # Initialize InfluxDB client
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        
        # In-memory cache for current state
        self._current_states: Dict[str, SensorData] = {}
        self._lot_configs: Dict[str, ParkingLotConfig] = {}
        self._adaptation_thresholds: Dict[str, Any] = {}
        
        logger.info(f"Knowledge Base initialized with InfluxDB at {url}")
    
    def store_sensor_data(self, sensor_data: SensorData):
        """
        Store sensor data from a parking lot.
        
        Args:
            sensor_data: SensorData object containing current lot state
        """
        try:
            point = (
                Point("parking_sensor_data")
                .tag("lot_id", sensor_data.lot_id)
                .field("occupancy_percentage", sensor_data.occupancy_percentage)
                .field("current_occupancy", sensor_data.current_occupancy)
                .field("total_capacity", sensor_data.total_capacity)
                .field("queue_length", sensor_data.queue_length)
                .field("rejected_count", sensor_data.rejected_count)
                .field("current_price", sensor_data.current_price)
                .field("revenue", sensor_data.revenue)
                .field("external_traffic_level", sensor_data.external_traffic_level)
                .field("gate_state", sensor_data.gate_state)
                # Don't set explicit timestamp - let InfluxDB use server time for consistency
                # .time(sensor_data.timestamp, WritePrecision.NS)
            )
            
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            
            # Update in-memory cache
            self._current_states[sensor_data.lot_id] = sensor_data
            
            logger.info(f"Stored sensor data for lot {sensor_data.lot_id} - Occ: {sensor_data.occupancy_percentage:.1f}%")
            
        except Exception as e:
            logger.error(f"Failed to store sensor data: {e}", exc_info=True)
    
    def store_adaptation_decision(self, decision: AdaptationDecision):
        """
        Store an adaptation decision made by the autonomic manager.
        
        Args:
            decision: AdaptationDecision object
        """
        try:
            point = (
                Point("adaptation_decisions")
                .tag("lot_id", decision.lot_id)
                .tag("trigger_condition", decision.trigger_condition)
                .field("actions", ",".join([a.value for a in decision.actions]))
                .field("expected_outcome", decision.expected_outcome)
                .field("confidence", decision.confidence)
                .field("occupancy", decision.current_state.get("occupancy_percentage", 0))
                .field("queue_length", decision.current_state.get("queue_length", 0))
                .field("price", decision.current_state.get("current_price", 0))
                # Use server time for consistency
                # .time(decision.timestamp, WritePrecision.NS)
            )
            
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.info(f"Stored adaptation decision for lot {decision.lot_id}: {[a.value for a in decision.actions]}")
            
        except Exception as e:
            logger.error(f"Failed to store adaptation decision: {e}")
    
    def store_system_metrics(self, metrics: SystemMetrics):
        """
        Store aggregated system metrics.
        
        Args:
            metrics: SystemMetrics object
        """
        try:
            point = (
                Point("system_metrics")
                .field("total_revenue", metrics.total_revenue)
                .field("total_occupancy", metrics.total_occupancy)
                .field("total_capacity", metrics.total_capacity)
                .field("overall_utilization", metrics.overall_utilization * 100)
                .field("total_rejected", metrics.total_rejected)
                .field("total_queue_length", metrics.total_queue_length)
                .field("average_price", metrics.average_price)
                .field("lots_at_capacity", metrics.lots_at_capacity)
                .field("lots_under_utilized", metrics.lots_under_utilized)
                # Use server time for consistency
                # .time(metrics.timestamp, WritePrecision.NS)
            )
            
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug("Stored system metrics")
            
        except Exception as e:
            logger.error(f"Failed to store system metrics: {e}")
    
    def get_current_state(self, lot_id: str) -> Optional[SensorData]:
        """
        Get the current state of a parking lot from cache.
        
        Args:
            lot_id: Parking lot identifier
            
        Returns:
            Latest SensorData or None if not available
        """
        return self._current_states.get(lot_id)
    
    def get_all_current_states(self) -> Dict[str, SensorData]:
        """
        Get current states of all parking lots.
        
        Returns:
            Dictionary mapping lot_id to SensorData
        """
        return self._current_states.copy()
    
    def get_historical_data(
        self, 
        lot_id: str, 
        start_time: datetime, 
        end_time: datetime = None,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query historical sensor data for a parking lot.
        
        Args:
            lot_id: Parking lot identifier
            start_time: Start of time range
            end_time: End of time range (defaults to now)
            fields: Specific fields to retrieve
            
        Returns:
            List of data points as dictionaries
        """
        if end_time is None:
            end_time = datetime.utcnow()
        
        field_filter = ""
        if fields:
            field_conditions = " or ".join([f'r._field == "{f}"' for f in fields])
            field_filter = f'|> filter(fn: (r) => {field_conditions})'
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
            |> filter(fn: (r) => r._measurement == "parking_sensor_data")
            |> filter(fn: (r) => r.lot_id == "{lot_id}")
            {field_filter}
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query(query, org=self.org)
            data = []
            for table in result:
                for record in table.records:
                    data.append(record.values)
            return data
        except Exception as e:
            logger.error(f"Failed to query historical data: {e}")
            return []
    
    def get_average_occupancy(self, lot_id: str, duration_minutes: int = 30) -> float:
        """
        Calculate average occupancy over a time period.
        
        Args:
            lot_id: Parking lot identifier
            duration_minutes: Time window in minutes
            
        Returns:
            Average occupancy percentage
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -{duration_minutes}m)
            |> filter(fn: (r) => r._measurement == "parking_sensor_data")
            |> filter(fn: (r) => r.lot_id == "{lot_id}")
            |> filter(fn: (r) => r._field == "occupancy_percentage")
            |> mean()
        '''
        
        try:
            result = self.query_api.query(query, org=self.org)
            for table in result:
                for record in table.records:
                    return record.get_value()
            return 0.0
        except Exception as e:
            logger.error(f"Failed to calculate average occupancy: {e}")
            return 0.0
    
    def get_trend(self, lot_id: str, field: str, duration_minutes: int = 15) -> str:
        """
        Determine the trend of a metric (increasing, decreasing, stable).
        
        Args:
            lot_id: Parking lot identifier
            field: Field name to analyze
            duration_minutes: Time window
            
        Returns:
            Trend indicator: "increasing", "decreasing", or "stable"
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -{duration_minutes}m)
            |> filter(fn: (r) => r._measurement == "parking_sensor_data")
            |> filter(fn: (r) => r.lot_id == "{lot_id}")
            |> filter(fn: (r) => r._field == "{field}")
            |> derivative(unit: 1m, nonNegative: false)
            |> mean()
        '''
        
        try:
            result = self.query_api.query(query, org=self.org)
            for table in result:
                for record in table.records:
                    derivative = record.get_value()
                    if derivative > 0.5:
                        return "increasing"
                    elif derivative < -0.5:
                        return "decreasing"
                    else:
                        return "stable"
            return "stable"
        except Exception as e:
            logger.debug(f"Could not determine trend: {e}")
            return "stable"
    
    def set_lot_config(self, config: ParkingLotConfig):
        """Store parking lot configuration"""
        self._lot_configs[config.id] = config
        logger.info(f"Stored configuration for lot {config.id}")
    
    def get_lot_config(self, lot_id: str) -> Optional[ParkingLotConfig]:
        """Retrieve parking lot configuration"""
        return self._lot_configs.get(lot_id)
    
    def set_adaptation_thresholds(self, thresholds: Dict[str, Any]):
        """Store adaptation thresholds"""
        self._adaptation_thresholds = thresholds
        logger.info("Updated adaptation thresholds")
    
    def get_adaptation_thresholds(self) -> Dict[str, Any]:
        """Retrieve adaptation thresholds"""
        return self._adaptation_thresholds.copy()
    
    def get_recent_adaptations(self, lot_id: str, duration_minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Get recent adaptation decisions for a lot.
        
        Args:
            lot_id: Parking lot identifier
            duration_minutes: Time window
            
        Returns:
            List of recent adaptations
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -{duration_minutes}m)
            |> filter(fn: (r) => r._measurement == "adaptation_decisions")
            |> filter(fn: (r) => r.lot_id == "{lot_id}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query(query, org=self.org)
            adaptations = []
            for table in result:
                for record in table.records:
                    adaptations.append(record.values)
            return adaptations
        except Exception as e:
            logger.error(f"Failed to get recent adaptations: {e}")
            return []
    
    def close(self):
        """Close the InfluxDB connection"""
        self.client.close()
        logger.info("Knowledge Base connection closed")
