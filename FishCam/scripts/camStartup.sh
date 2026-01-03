#!/bin/bash
# FishCam Startup Script
# This script is executed on boot via cron job

# Initial delay to let system stabilize
sleep 10

# Change to scripts directory
cd /home/fishcam/Desktop/FishCam/FishCam/scripts/

# Start power saving mode controller in background
echo "Starting power saving controller..."
sudo python3 ./powerSavingMode.py >> ../logs/power_saving_startup.log 2>&1 &

# Wait for power saving controller to initialize
# This ensures WiFi/services are in correct state before video capture starts
sleep 5

# Start video capture (runs in foreground)
echo "Starting video capture..."
python3 ./captureVideo.py
