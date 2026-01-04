#!/bin/bash
# FishCam Startup Script
# This script is executed on boot via cron job

# Initial delay to let system stabilize
sleep 10

# Change to scripts directory
cd /home/fishcam/Desktop/FishCam/FishCam/scripts/

# Create logs directory if it doesn't exist
mkdir -p ../logs

# Auto-connect to WiFi if configured
echo "Checking WiFi auto-connect configuration..."
python3 - << 'PYEOF'
import yaml
import subprocess
import sys

try:
    with open('fishcam_config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    power_saving = config.get('power_saving', {})
    wifi_auto_connect = power_saving.get('wifi_auto_connect', False)
    wifi_ssid = power_saving.get('wifi_ssid', '')
    wifi_password = power_saving.get('wifi_password', '')

    if wifi_auto_connect and wifi_ssid and wifi_password:
        print(f"Connecting to WiFi: {wifi_ssid}")
        result = subprocess.run(
            f'nmcli device wifi connect "{wifi_ssid}" password "{wifi_password}"',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"Successfully connected to {wifi_ssid}")
        else:
            print(f"Failed to connect: {result.stderr}")
    else:
        print("WiFi auto-connect not configured or disabled")
except Exception as e:
    print(f"WiFi auto-connect error: {e}")
PYEOF

# Start power saving mode controller in background
# Check if already running to avoid GPIO conflicts
if pgrep -f "powerSavingMode.py" > /dev/null; then
    echo "Power saving controller already running, skipping..."
else
    echo "Starting power saving controller..."
    sudo python3 ./powerSavingMode.py >> ../logs/power_saving_startup.log 2>&1 &
fi

# Wait for power saving controller to initialize
# This ensures WiFi/services are in correct state before video capture starts
sleep 5

# Start video capture (runs in foreground)
echo "Starting video capture..."
python3 ./captureVideo.py
