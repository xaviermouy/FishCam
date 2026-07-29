#!/bin/bash
# FishCam Startup Script
# This script is executed on boot via cron job

# Initial delay to let system stabilize
sleep 30

# Resolve script directory so this works regardless of where cron calls it from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Read data/log directory paths from fishcam_config.yaml via config.py
VIDEO_DIR=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['video_dir'])")
LOG_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['log_dir'])")
IMU_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['imu_dir'])")
GPS_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['gps_dir'])")

# Create data subdirectories
mkdir -p "$VIDEO_DIR" "$LOG_DIR" "$IMU_DIR" "$GPS_DIR"

# Auto-connect to WiFi if configured AND power saving mode is disabled
# If power saving is enabled, powerSavingMode.py will handle WiFi based on reed switch
echo "Checking WiFi auto-connect configuration..."
python3 - << 'PYEOF'
import yaml
import subprocess
import sys

try:
    with open('fishcam_config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    power_saving = config.get('power_saving', {})
    power_saving_enabled = power_saving.get('enabled', False)
    wifi_auto_connect = power_saving.get('wifi_auto_connect', False)
    wifi_ssid = power_saving.get('wifi_ssid', '')
    wifi_password = power_saving.get('wifi_password', '')

    # Only auto-connect at boot if power saving mode is disabled
    # When power saving is enabled, let powerSavingMode.py handle WiFi
    if not power_saving_enabled and wifi_auto_connect and wifi_ssid and wifi_password:
        print(f"Power saving disabled - connecting to WiFi: {wifi_ssid}")
        result = subprocess.run(
            f'nmcli device wifi connect "{wifi_ssid}" password "{wifi_password}" wpa-psk',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"Successfully connected to {wifi_ssid}")
        else:
            print(f"Failed to connect: {result.stderr}")
    elif power_saving_enabled:
        print("Power saving enabled - WiFi will be controlled by powerSavingMode.py based on reed switch")
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
    sudo python3 ./powerSavingMode.py >> "$LOG_DIR/power_saving_startup.log" 2>&1 &
fi

# Wait for power saving controller to initialize
# This ensures WiFi/services are in correct state before video capture starts
sleep 5

# Start IMU acquisition in background (if enabled in config)
if pgrep -f "imuAcquisition.py" > /dev/null; then
    echo "IMU acquisition already running, skipping..."
else
    echo "Starting IMU acquisition..."
    python3 ./imuAcquisition.py >> "$LOG_DIR/imu_startup.log" 2>&1 &
fi

# Start video capture (runs in foreground)
echo "Starting video capture..."
python3 ./captureVideo.py
