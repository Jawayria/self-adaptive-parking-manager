"""
Main Entry Point for Self-Adaptive Smart Parking Lot Manager

This script starts both the parking lot simulators and the autonomic manager.
"""

import sys
import signal
import logging
import time
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models import ParkingLotConfig
from src.mqtt_client import MQTTClient
from src.knowledge_base import KnowledgeBase
from src.parking_simulator import ParkingSystemSimulator
from src.autonomic_manager import MAPEKAutonomicManager


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
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('parking_system.log')
        ]
    )


def main():
    """Main entry point"""
    # Load configuration
    config = load_config()
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Self-Adaptive Smart Parking Lot Manager")
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
    
    # Initialize MQTT client for autonomic manager
    manager_mqtt = MQTTClient(
        broker=mqtt_config['broker'],
        port=mqtt_config['port'],
        client_id="autonomic_manager"
    )
    
    # Initialize Knowledge Base
    influx_config = config['influxdb']
    knowledge_base = KnowledgeBase(
        url=influx_config['url'],
        token=influx_config['token'],
        org=influx_config['org'],
        bucket=influx_config['bucket']
    )
    
    # Initialize Parking System Simulator
    simulator = ParkingSystemSimulator(
        lot_configs=lot_configs,
        mqtt_client=simulator_mqtt,
        simulation_params=config['simulation']
    )
    
    # Initialize Autonomic Manager
    autonomic_manager = MAPEKAutonomicManager(
        mqtt_client=manager_mqtt,
        knowledge_base=knowledge_base,
        lot_configs=lot_configs,
        adaptation_config=config['adaptation']
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
        # Connect MQTT clients
        logger.info("Connecting to MQTT broker...")
        simulator_mqtt.connect()
        simulator_mqtt.start()
        
        manager_mqtt.connect()
        manager_mqtt.start()
        
        # Wait for connections
        time.sleep(2)
        
        # Start simulator
        logger.info("Starting parking lot simulators...")
        simulator.start_all()
        
        # Start autonomic manager
        logger.info("Starting Autonomic Manager (MAPE-K Loop)...")
        autonomic_manager.start()
        
        logger.info("=" * 60)
        logger.info("System running. Press Ctrl+C to stop.")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Grafana Dashboard: http://localhost:3000")
        logger.info("  Username: admin, Password: admin")
        logger.info("")
        logger.info("InfluxDB UI: http://localhost:8086")
        logger.info("  Username: admin, Password: adminpassword123")
        logger.info("")
        
        # Main loop
        while running:
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
        
    finally:
        # Cleanup
        logger.info("Shutting down...")
        autonomic_manager.stop()
        simulator.stop_all()
        simulator_mqtt.stop()
        simulator_mqtt.disconnect()
        manager_mqtt.stop()
        manager_mqtt.disconnect()
        knowledge_base.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
