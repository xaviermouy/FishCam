#!/bin/bash
# FishCam Startup Script
# This script is executed on boot via cron job

# Initial delay to let system stabilize
sleep 10

# Change to scripts directory
cd /home/fishcam/Desktop/FishCam/FishCam/scripts/

# Create logs directory if it doesn't exist
mkdir -p ../logs

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
