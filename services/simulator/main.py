"""
Parking Lot Simulator Service for Self-Adaptive Smart Parking Lot Manager

This service runs the parking lot simulators that generate sensor data
and respond to control commands from the MAPE-K services.
"""

import sys
import signal
import logging
import time
import yaml
from pathlib import Path

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import ParkingLotConfig
from src.mqtt_client import MQTTClient
from src.parking_simulator import ParkingSystemSimulator


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    """Configure logging based on config"""
    log_config = config.get('logging', {})
    level = getattr(logging, log_config.get('level', 'INFO'))
    format_str = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler()]
    )


def main():
    """Main entry point"""
    config = load_config()
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Parking Lot Simulator Service")
    logger.info("=" * 60)
    
    # Parse parking lot configurations
    lot_configs = [
        ParkingLotConfig.from_dict(lot_data)
        for lot_data in config['parking_lots']
    ]
    
    # Initialize MQTT client for simulator
    mqtt_config = config['mqtt']
    simulator_mqtt = MQTTClient(
        broker=mqtt_config['broker'],
        port=mqtt_config['port'],
        client_id="parking_simulator"
    )
    
    # Initialize Parking System Simulator
    simulator = ParkingSystemSimulator(
        lot_configs=lot_configs,
        mqtt_client=simulator_mqtt,
        simulation_params=config['simulation']
    )
    
    # Graceful shutdown handler
    running = True
    
    def signal_handler(signum, frame):
        nonlocal running
        logger.info("Received shutdown signal")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Connect MQTT client
        logger.info("Connecting to MQTT broker...")
        simulator_mqtt.connect()
        simulator_mqtt.start()
        
        # Wait for connection
        time.sleep(2)
        
        # Start simulator
        logger.info("Starting parking lot simulators...")
        simulator.start_all()
        
        logger.info("=" * 60)
        logger.info("Simulator running.")
        logger.info("=" * 60)
        
        # Main loop
        while running:
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
        
    finally:
        # Cleanup
        logger.info("Shutting down...")
        simulator.stop_all()
        simulator_mqtt.stop()
        simulator_mqtt.disconnect()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
