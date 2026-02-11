"""
MQTT Client Wrapper for Self-Adaptive Smart Parking Lot Manager

This module provides a unified interface for MQTT communication between
the parking lot simulator and the autonomic manager.
"""

import json
import logging
from typing import Callable, Dict, Any, Optional
import paho.mqtt.client as mqtt
from datetime import datetime

logger = logging.getLogger(__name__)


class MQTTClient:
    """
    MQTT Client wrapper for parking lot management system.
    
    Handles connection, subscription, and message publishing for both
    sensor data and control commands.
    """
    
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        client_id: str = None,
        on_connect_callback: Callable = None,
        on_message_callback: Callable = None
    ):
        """
        Initialize MQTT client.
        
        Args:
            broker: MQTT broker hostname
            port: MQTT broker port
            client_id: Unique client identifier
            on_connect_callback: Callback for connection events
            on_message_callback: Callback for received messages
        """
        self.broker = broker
        self.port = port
        self.client_id = client_id or f"parking_client_{datetime.now().timestamp()}"
        
        # Create MQTT client
        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Store user callbacks
        self._user_on_connect = on_connect_callback
        self._user_on_message = on_message_callback
        
        # Topic-specific callbacks
        self._topic_callbacks: Dict[str, Callable] = {}
        
        # Connection status
        self._connected = False
        
        logger.info(f"MQTT Client initialized with ID: {self.client_id}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Internal callback for connection events"""
        if rc == 0:
            self._connected = True
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            
            # Re-subscribe to topics after reconnection
            for topic in self._topic_callbacks.keys():
                self.client.subscribe(topic)
                logger.debug(f"Re-subscribed to topic: {topic}")
        else:
            self._connected = False
            error_messages = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            logger.error(f"Connection failed: {error_msg}")
        
        # Call user callback if provided
        if self._user_on_connect:
            self._user_on_connect(client, userdata, flags, rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """Internal callback for disconnection events"""
        self._connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker (rc={rc})")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_message(self, client, userdata, msg):
        """Internal callback for received messages"""
        topic = msg.topic
        try:
            # Try to parse as JSON
            payload = json.loads(msg.payload.decode('utf-8'))
        except json.JSONDecodeError:
            # If not JSON, use raw payload
            payload = msg.payload.decode('utf-8')
        
        logger.debug(f"Received message on topic '{topic}': {payload}")
        
        # Check for topic-specific callback
        for subscribed_topic, callback in self._topic_callbacks.items():
            if mqtt.topic_matches_sub(subscribed_topic, topic):
                callback(topic, payload)
                return
        
        # Fall back to user callback
        if self._user_on_message:
            self._user_on_message(topic, payload)
    
    def connect(self) -> bool:
        """
        Connect to the MQTT broker.
        
        Returns:
            True if connection initiated successfully, False otherwise
        """
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, keepalive=60)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the MQTT broker"""
        self.client.disconnect()
        self._connected = False
        logger.info("Disconnected from MQTT broker")
    
    def start(self):
        """Start the MQTT client loop in a background thread"""
        self.client.loop_start()
        logger.info("MQTT client loop started")
    
    def stop(self):
        """Stop the MQTT client loop"""
        self.client.loop_stop()
        logger.info("MQTT client loop stopped")
    
    def subscribe(self, topic: str, callback: Callable[[str, Any], None] = None, qos: int = 1):
        """
        Subscribe to an MQTT topic.
        
        Args:
            topic: Topic pattern to subscribe to (supports wildcards)
            callback: Callback function for messages on this topic
            qos: Quality of Service level (0, 1, or 2)
        """
        if callback:
            self._topic_callbacks[topic] = callback
        
        result, mid = self.client.subscribe(topic, qos)
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Failed to subscribe to topic: {topic}")
    
    def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic"""
        if topic in self._topic_callbacks:
            del self._topic_callbacks[topic]
        self.client.unsubscribe(topic)
        logger.info(f"Unsubscribed from topic: {topic}")
    
    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False):
        """
        Publish a message to an MQTT topic.
        
        Args:
            topic: Topic to publish to
            payload: Message payload (will be JSON encoded if dict/list)
            qos: Quality of Service level
            retain: Whether to retain the message on the broker
        """
        if isinstance(payload, (dict, list)):
            message = json.dumps(payload)
        else:
            message = str(payload)
        
        result = self.client.publish(topic, message, qos=qos, retain=retain)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Published to '{topic}': {message[:100]}...")
        else:
            logger.error(f"Failed to publish to '{topic}': rc={result.rc}")
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected to broker"""
        return self._connected


class ParkingMQTTTopics:
    """
    Centralized definition of MQTT topics used in the parking system.
    """
    
    # Topic templates
    SENSOR_DATA = "parking/lot/{lot_id}/sensors"
    CONTROL_COMMANDS = "parking/lot/{lot_id}/control"
    STATUS = "parking/lot/{lot_id}/status"
    SYSTEM_METRICS = "parking/system/metrics"
    ADAPTATION_LOG = "parking/system/adaptations"
    
    @classmethod
    def get_sensor_topic(cls, lot_id: str) -> str:
        """Get sensor data topic for a specific lot"""
        return cls.SENSOR_DATA.format(lot_id=lot_id)
    
    @classmethod
    def get_control_topic(cls, lot_id: str) -> str:
        """Get control commands topic for a specific lot"""
        return cls.CONTROL_COMMANDS.format(lot_id=lot_id)
    
    @classmethod
    def get_status_topic(cls, lot_id: str) -> str:
        """Get status topic for a specific lot"""
        return cls.STATUS.format(lot_id=lot_id)
    
    @classmethod
    def get_all_sensors_topic(cls) -> str:
        """Get wildcard topic for all sensor data"""
        return "parking/lot/+/sensors"
    
    @classmethod
    def get_all_control_topic(cls) -> str:
        """Get wildcard topic for all control commands"""
        return "parking/lot/+/control"
