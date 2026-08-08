#!/bin/bash
# FishCam Startup Script
# This script is executed on boot via cron job

# Initial delay to let system stabilize
sleep 10

# Sync system clock from WittyPi RTC (DS3231) before anything time-sensitive runs
WITTYPI_UTILS="/home/fishcam/Desktop/wittypi/utilities.sh"
if [ -f "$WITTYPI_UTILS" ]; then
    bash -c "source \"$WITTYPI_UTILS\" && rtc_to_system" \
        && echo "System clock synced from WittyPi RTC" \
        || echo "WARNING: Failed to sync system clock from WittyPi RTC (non-fatal)"
else
    echo "WARNING: WittyPi utilities.sh not found — skipping RTC sync"
fi

# Resolve script directory so this works regardless of where cron calls it from
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Read directory paths from fishcam_config.yaml via config.py
VIDEO_DIR=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['video_dir'])")
LOG_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['log_dir'])")
IMU_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['imu_dir'])")
GPS_DIR=$(python3   -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_paths()['gps_dir'])")
WITTYPI_DIR=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_wittypi_settings()['install_dir'])" 2>/dev/null)

# Guard: abort if config failed to load (empty paths would create wrong directories)
if [ -z "$LOG_DIR" ] || [ -z "$VIDEO_DIR" ]; then
    echo "ERROR: Failed to load configuration from fishcam_config.yaml. Aborting startup." >&2
    exit 1
fi

# Create data subdirectories
mkdir -p "$VIDEO_DIR" "$LOG_DIR" "$IMU_DIR" "$GPS_DIR"

# --- Copy logs from previous boot (each copy is independent; failures are non-fatal) ---

# System kernel journal: OOM kills, I2C errors, kernel panics, watchdog resets
# Overwrites the same file each boot — no accumulation, always reflects the last boot.
JOURNAL_LOG="$LOG_DIR/journal_$(hostname)_$(date +%Y%m%dT%H%M%S).log"
journalctl -b -1 -k --no-pager > "$JOURNAL_LOG" 2>/dev/null \
    && echo "Journal log saved: $JOURNAL_LOG" \
    || { echo "WARNING: Could not save journal log (no previous boot in journal yet)"; rm -f "$JOURNAL_LOG"; }

# WittyPi logs (cumulative — overwrites previous copy each boot)
# Copies all .log files found in the WittyPi directory (robust to filename changes across versions)
if [ -n "$WITTYPI_DIR" ]; then
    found=0
    for log_file in "$WITTYPI_DIR"/*.log; do
        [ -f "$log_file" ] || continue  # skip if glob matched nothing
        dest="$LOG_DIR/wittypi_$(hostname)_$(basename "$log_file")"
        cp "$log_file" "$dest" 2>/dev/null \
            && { echo "WittyPi log copied: $(basename "$log_file")"; found=1; } \
            || echo "WARNING: Could not copy $(basename "$log_file") (non-fatal)"
    done
    [ "$found" -eq 0 ] && echo "WARNING: No .log files found in $WITTYPI_DIR (non-fatal)"
else
    echo "WARNING: WittyPi log_dir not configured or could not be read (non-fatal)"
fi

# Connect to WiFi if configured (skips automatically if power saving mode is enabled)
python3 ./run_network.py

# Sync WittyPi RTC from NTP if WiFi is up and enabled in config
# Skips instantly if WiFi is down (power saving mode) or interval not elapsed
python3 ./sync_rtc.py

# Fix wittyPi.log ownership before run_power_manager.py starts.
# run_power_manager.py runs as root; if a previous boot left wittyPi.log
# owned by root, configure_wittypi.py (run as fishcam) will fail with
# "Permission denied". Reset ownership to the current user at each boot.
if [ -n "$WITTYPI_DIR" ] && [ -d "$WITTYPI_DIR" ]; then
    sudo chown "$USER:$USER" "$WITTYPI_DIR/wittyPi.log" 2>/dev/null || true
fi

# Start power saving mode controller in background
if pgrep -f "run_power_manager.py" > /dev/null; then
    echo "Power saving controller already running, skipping..."
else
    echo "Starting power saving controller..."
    sudo python3 ./run_power_manager.py >> "$LOG_DIR/power_saving_$(hostname).log" 2>&1 &
fi

# Wait for power saving controller to initialize
sleep 5

# Start IMU acquisition in background (if enabled in config)
if pgrep -f "run_imu.py" > /dev/null; then
    echo "IMU acquisition already running, skipping..."
else
    echo "Starting IMU acquisition..."
    python3 ./run_imu.py >> "$LOG_DIR/imu_$(hostname).log" 2>&1 &
fi

# Start buzzer controller in background (if enabled in config)
if pgrep -f "run_buzzer.py" > /dev/null; then
    echo "Buzzer controller already running, skipping..."
else
    echo "Starting buzzer controller..."
    python3 ./run_buzzer.py >> "$LOG_DIR/buzzer_$(hostname).log" 2>&1 &
fi

# Start video capture (runs in foreground)
echo "Starting video capture..."
python3 ./run_video.py
