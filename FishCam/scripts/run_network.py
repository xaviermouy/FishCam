#!/usr/bin/env python3
"""
FishCam Network Manager

Handles WiFi connection at boot. Called once by fishcamStartup.sh.

Behaviour:
  - If power saving mode is enabled, skip (run_power_manager.py controls
    WiFi based on the reed switch state).
  - If power saving is disabled and wifi_auto_connect is true, connect to
    the configured network using nmcli.

Configuration (fishcam_config.yaml):
  network.wifi_auto_connect : true/false
  network.wifi_ssid         : WiFi network name
  network.wifi_password     : WiFi password
  power_saving.enabled      : if true, this script does nothing
"""

import logging
import subprocess
import sys
from pathlib import Path

import config


def connect_wifi(ssid, password):
    """Attempt to connect to a WiFi network via nmcli. Returns True on success."""
    result = subprocess.run(
        f'nmcli device wifi connect "{ssid}" password "{password}"',
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logging.info(f"Connected to WiFi network: {ssid}")
        return True
    else:
        logging.warning(f"Failed to connect to {ssid}: {result.stderr.strip()}")
        return False


def main():
    log_dir = Path(__file__).parent / config.get_paths()['log_dir']
    log_dir.mkdir(parents=True, exist_ok=True)
    fishcam_id = config.get_fishcam_id()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_dir / f'network_{fishcam_id}.log'),
            logging.StreamHandler(sys.stdout),
        ]
    )

    power_saving = config.get_power_saving_settings()
    network      = config.get_network_settings()

    if power_saving['enabled']:
        logging.info("Power saving enabled — WiFi managed by run_power_manager.py. Skipping.")
        return

    if not network['wifi_auto_connect']:
        logging.info("WiFi auto-connect disabled in configuration. Skipping.")
        return

    if not network['wifi_ssid'] or not network['wifi_password']:
        logging.warning("wifi_auto_connect is true but ssid or password is not set. Skipping.")
        return

    logging.info(f"Connecting to WiFi: {network['wifi_ssid']}")
    connect_wifi(network['wifi_ssid'], network['wifi_password'])


if __name__ == '__main__':
    main()
