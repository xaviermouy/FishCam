# FishCam - Autonomous Underwater Video Recording System

## Overview

FishCam is an autonomous underwater video recording system designed for long-term deployment in marine environments. It runs on a Raspberry Pi Zero 2W and captures video, IMU orientation data, and acoustic buzzer sequences for multi-unit synchronization.

**Original FishCam code**: https://github.com/xaviermouy/fishcam_2020_paper

---

## Repository Layout

```
FishCam/
  scripts/               # All deployable scripts (run from this directory)
    utils/               # Post-processing and diagnostic utilities
    fishcam_config.yaml  # Master configuration file
    fishcamStartup.sh    # Boot-time startup orchestration
  wittypi_schedules/     # WittyPi on/off schedule files (.wpi)
  POWER_SAVING_SETUP.md  # Power saving hardware setup guide
  fishcam_setup_steps.txt # Complete setup checklist
```

At runtime, data is written relative to the scripts directory:
```
../data/video/   # H.264 / MJPEG video files + per-video _metadata.json
../data/logs/    # Timestamped .log files, power_saving.log, imu_acquisition.log
../data/imu/     # BNO085 IMU CSV files
```

---

## Scripts

### Core Acquisition

| Script | Description |
|--------|-------------|
| **`run_video.py`** | Main video capture. Records continuously, producing H.264/MJPEG clips with per-frame metadata JSON files. Includes retry logic for transient camera errors. |
| **`run_imu.py`** | Reads Adafruit BNO085 IMU over I2C. Writes CSV rows (quaternion, Euler angles, accel, gyro, mag). Flushes every 50 samples. Auto-recovers from I2C crashes. |
| **`run_buzzer.py`** | Acoustic sequence controller. Fires at configured trigger times daily. Supports m-sequence (LFSR-based, recommended) and legacy beep modes. |
| **`run_power_manager.py`** | Monitors reed switch to toggle between power-saving and configuration modes. Controls WiFi, Bluetooth, HDMI, CPU frequency, services. |
| **`run_network.py`** | Connects to WiFi at boot via nmcli. Skipped when power saving mode manages WiFi state. |
| **`run_api.py`** | Flask HTTP API serving system status and the web dashboard on port 5000. |

### Startup

| Script | Description |
|--------|-------------|
| **`fishcamStartup.sh`** | Boot-time orchestration (via cron). Syncs RTC, creates directories, connects WiFi, then starts background processes (power manager, IMU, buzzer, API) and video capture in foreground. |

### Setup and Deployment

| Script | Description |
|--------|-------------|
| **`start_new_deployment.py`** | Interactive 9-step pre-deployment wizard: verify identity, timezone, buzzer schedule, IMU calibration, WittyPi config, clear data/logs, optional reboot. |
| **`configure_wittypi.py`** | WittyPi setup: RTC sync, power schedule, voltage protection, daily on/off windows. |
| **`sync_rtc.py`** | Boot-time RTC sync from NTP (called by fishcamStartup.sh). |
| **`delete_data.py`** | Safe data deletion with confirmation prompt. |
| **`verify_fishcam.sh`** | System verification and auto-fix: packages, cron, repo, permissions, hostname, I2C. |
| **`updateFishCamRepo.sh`** | Fetches and resets to origin/main. |
| **`clear_system_logs.sh`** | Clears systemd journal (pre-deployment). |
| **`clear_wittypi_logs.sh`** | Clears WittyPi logs (pre-deployment). |

### Monitoring and Diagnostics

| Script | Description |
|--------|-------------|
| **`monitor_system.py`** | Real-time curses dashboard: process status, log tails, hardware health, storage, buzzer schedule. |
| **`monitor_imu.py`** | Real-time IMU data display: orientation, accel, gyro, mag, calibration status. |
| **`calibrate_imu.py`** | Interactive IMU calibration with magnetometer coverage tracking. Auto-saves to BNO085 NVRAM. |
| **`dashboard.html`** | Web-based monitoring interface. Auto-discovers all fishcams on the network (fishcam01..20.local). |
| **`system_status.py`** | Shared status collection module used by both the CLI monitor and the web API. |

### Utility Modules

| Script | Description |
|--------|-------------|
| **`config.py`** | Configuration singleton. Loads `fishcam_config.yaml`. FishCam ID derived from hostname. |
| **`buzzer_utils.py`** | Shared buzzer timing helpers (trigger parsing, schedule display). No hardware dependencies. |
| **`wittypi_utils.py`** | WittyPi hardware interface: RTC sync, WiFi/NTP checks, voltage reading. |

### Post-Processing Utilities (`utils/`)

| Script | Description |
|--------|-------------|
| **`convertH264toMP4.py`** | Convert H.264 video files to MP4. |
| **`convertH264toMP4_ffmpeg.py`** | Convert H.264 to MP4 using ffmpeg. |
| **`parse_camera_logs.py`** | Extract frame statistics, dropped frames, and buzzer events from logs. |
| **`parse_wittypi_log.py`** | Parse WittyPi log files. |
| **`check_power_status.sh`** | Report current power saving status. |

---

## Configuration File: `fishcam_config.yaml`

### Deployment Timezone

```yaml
deployment_timezone: "America/New_York"
```

The Pi always runs in UTC. This timezone is used to interpret all local times in the config (WittyPi deployment window, daily schedule, buzzer trigger times). Must be a valid IANA timezone name.

---

### Video Capture Settings

```yaml
video:
  duration: 900
  resolution: [1920, 1080]
  frameRate: 10
  quality: 'medium'
  format: 'h264'
```

- **`duration`**: Duration of each video clip in seconds.
- **`resolution`**: Video resolution `[width, height]` in pixels.
- **`frameRate`**: Frame rate in frames per second.
- **`quality`**: Encoding quality. Options: `'very_low'`, `'low'`, `'medium'`, `'high'`, `'very_high'`.
- **`format`**: Video format. Options: `'h264'` or `'mjpeg'`.

---

### Camera Control Settings

```yaml
camera:
  sharpness: 1.0
  contrast: 1.0
  brightness: 0.0
  saturation: 1.0
  AnalogueGain: 8.0
  AeEnable: true
  AeExposureMode: 0
  AwbEnable: true
  AwbMode: 0
  vflip: false
  hflip: false
```

- **`sharpness`**: 0.0 to 16.0 (default: 1.0).
- **`contrast`**: 0.0 to 32.0 (default: 1.0).
- **`brightness`**: -1.0 to 1.0 (default: 0.0).
- **`saturation`**: 0.0 to 32.0 (default: 1.0).
- **`AnalogueGain`**: Analogue gain, 1.0 to 16.0 (replaces ISO).
- **`AeEnable`**: Auto exposure (true/false).
- **`AeExposureMode`**: 0=Normal, 1=Short, 2=Long, 3=Custom.
- **`AwbEnable`**: Auto white balance (true/false).
- **`AwbMode`**: 0=Auto, 1=Tungsten, 2=Fluorescent, 3=Indoor, 4=Daylight, 5=Cloudy, 6=Custom.
- **`vflip`** / **`hflip`**: Vertical/horizontal flip (true/false).

---

### Network Settings

```yaml
network:
  wifi_auto_connect: true
  wifi_ssid: "FishcamNetwork"
  wifi_password: "your_password"
```

- **`wifi_auto_connect`**: Automatically connect to WiFi on boot / when entering config mode.
- **`wifi_ssid`**: WiFi network name.
- **`wifi_password`**: WiFi password (stored in plaintext -- avoid committing real credentials).

---

### Buzzer Settings

```yaml
buzzer:
  enabled: true
  pin: 26
  sequence_mode: 'msequence'

  # M-sequence parameters
  msequence_n: 6
  chip_duration_sec: 0.1

  # Legacy beep parameters
  beep_count: 4
  beep_duration_sec: 0.1
  beep_gap_sec: 0.1

  # Schedule
  trigger_times:
    - "00:00"
    - "06:00"
    - "12:00"
    - "18:00"

  number_sequences: 5
  gap_between_sequences_sec: 5
  missed_trigger_grace_sec: 60
```

- **`enabled`**: Enable/disable buzzer (true/false).
- **`pin`**: GPIO pin for buzzer (BCM numbering).
- **`sequence_mode`**: `'msequence'` (recommended) or `'beep'` (legacy).

#### M-Sequence Mode (`sequence_mode: 'msequence'`)

Each unit plays a unique maximal-length LFSR sequence derived automatically from the unit number in the hostname (e.g., fishcam02 -> unit 2). Provides excellent autocorrelation properties for TDOA cross-correlation. No per-unit config edit needed.

- **`msequence_n`**: LFSR shift register length. Sequence length = 2^n - 1. n=5 -> 31 chips, n=6 -> 63 chips.
- **`chip_duration_sec`**: Duration of each chip (on or off) in seconds.

#### Legacy Beep Mode (`sequence_mode: 'beep'`)

Each unit plays a fixed number of beeps. Requires `beep_count` set uniquely per unit.

- **`beep_count`**: Number of beeps per sequence (must be unique per fishcam).
- **`beep_duration_sec`**: Duration of each beep in seconds.
- **`beep_gap_sec`**: Silence between beeps within a sequence.

#### Scheduling

- **`trigger_times`**: List of HH:MM times (local/deployment timezone) when the buzzer fires each day.
- **`number_sequences`**: Number of sequence repetitions per trigger.
- **`gap_between_sequences_sec`**: Gap between sequence repetitions.
- **`missed_trigger_grace_sec`**: Fire a late trigger if it was scheduled within this many seconds ago (0 = disabled).

---

### Power Saving Mode Settings

```yaml
power_saving:
  enabled: true
  reed_switch_pin: 24
  led_pin: 23
  check_interval: 2.0
  cpu_freq_power_saving: 800
  cpu_freq_config: 1000

  components:
    disable_wifi: true
    disable_bluetooth: true
    disable_hdmi: false
    disable_usb: false
    throttle_cpu: true
    stop_services: true
    disable_led_triggers: false
```

- **`enabled`**: Enable/disable power saving mode (requires reed switch hardware).
- **`reed_switch_pin`**: GPIO pin for reed switch (BCM numbering).
- **`led_pin`**: GPIO pin for status LED (BCM numbering).
- **`check_interval`**: How often to check reed switch state (seconds).
- **`cpu_freq_power_saving`** / **`cpu_freq_config`**: CPU frequency in MHz for each mode (Pi Zero 2W range: 600-1000 MHz).

**Component controls** -- each can be individually toggled:

| Component | Savings | Description |
|-----------|---------|-------------|
| `disable_wifi` | ~40-50 mA | Disable WiFi via nmcli |
| `disable_bluetooth` | ~10-15 mA | Disable Bluetooth |
| `disable_hdmi` | ~20-30 mA | Disable HDMI output |
| `disable_usb` | ~20-30 mA | USB autosuspend |
| `throttle_cpu` | ~50-100 mA | Throttle CPU frequency |
| `stop_services` | ~10-20 mA | Stop non-essential services |
| `disable_led_triggers` | minimal | Disable activity LED triggers |

See [POWER_SAVING_SETUP.md](FishCam/POWER_SAVING_SETUP.md) for hardware wiring and setup.

---

### IMU Settings

```yaml
imu:
  enabled: true
  i2c_address: 0x4A
  sample_rate_hz: 1

  reports:
    accelerometer: false
    gyroscope: false
    magnetometer: false
    rotation_vector: true
    linear_acceleration: false
    gravity: false
```

- **`enabled`**: Enable/disable IMU acquisition.
- **`i2c_address`**: I2C address (0x4A default, 0x4B if ADDR pin is high).
- **`sample_rate_hz`**: Sampling rate in Hz (1-50 Hz, BNO085 hardware limited).
- **`reports`**: Enable/disable individual sensor reports. Disabling unused ones reduces file size (~47 MB/hour at 50 Hz with all enabled).

**Wiring**: VIN -> 3.3V (Pin 1), GND -> GND (Pin 6), SDA -> GPIO2 (Pin 3), SCL -> GPIO3 (Pin 5).

---

### WittyPi Settings

```yaml
wittypi:
  install_dir: '/home/fishcam/Desktop/wittypi'
  i2c_address: 0x08
  power_cut_delay_sec: 60
  low_voltage_cutoff_v: 0
  recovery_voltage_v: 0
  voltage_log_interval_min: 10
  auto_sync_rtc_from_internet: true
  auto_sync_rtc_from_gps: false
  rtc_sync_min_interval_min: 15

  deployment:
    start: "2026-08-01 06:00:00"
    end:   "2026-09-30 23:59:59"

  daily_schedule:
    anchor_time: "06:00"
    windows:
      - name: "daytime"
        duration_hours: 14
        on_min: 15
        off_min: 45
      - name: "nighttime"
        duration_hours: 10
        on_min: 5
        off_min: 115
```

- **`power_cut_delay_sec`**: Seconds WittyPi waits after SIGTERM before hard power cut. Must allow clean shutdown (~15s) + margin.
- **`low_voltage_cutoff_v`** / **`recovery_voltage_v`**: Battery voltage protection thresholds (set both to 0 to disable).
- **`voltage_log_interval_min`**: How often to log input voltage to CSV.
- **`auto_sync_rtc_from_internet`**: Sync RTC from NTP at boot if WiFi is up.
- **`rtc_sync_min_interval_min`**: Minimum minutes between RTC syncs (prevents excessive I2C writes).
- **`deployment`**: Start and end dates (local timezone) for the deployment window.
- **`daily_schedule`**: Daily on/off cycling. Windows must sum to 24 hours. `anchor_time` is the local time where the sequence restarts each day.

---

### File Paths

```yaml
paths:
  video_dir: '../data/video'
  log_dir: '../data/logs'
  imu_dir: '../data/imu'
  gps_dir: '../data/gps'
```

### API Settings

```yaml
api:
  port: 5000
```

---

## Quick Start

1. **Install dependencies** (on the Pi):
   ```bash
   sudo apt install python3 cron git
   pip install pyyaml picamera2 lgpio flask
   pip install adafruit-blinka adafruit-circuitpython-bno08x
   ```

2. **Edit configuration**: Modify `fishcam_config.yaml` with your settings.

3. **Run the system**:
   ```bash
   cd /home/fishcam/Desktop/FishCam/FishCam/scripts
   python run_video.py
   ```

4. **Or run the full startup** (all subsystems):
   ```bash
   sh fishcamStartup.sh
   ```

---

## Monitoring

### CLI System Monitor

```bash
python monitor_system.py
# Press r to refresh, q to quit
```

Shows process status, log tails, hardware health (camera, I2C, voltage, CPU), storage, and buzzer schedule.

### CLI IMU Monitor

```bash
python monitor_imu.py
# Press q to quit
```

Live orientation, accelerometer, gyroscope, magnetometer readings. Safe to run anytime -- reads from I2C directly or from the live CSV when `run_imu.py` is active.

### Web Dashboard

Open `dashboard.html` in a browser while on the same WiFi network. Auto-discovers all fishcams (fishcam01..20.local) and displays processes, acquisition status, hardware, and logs.

Each fishcam runs a local API on port 5000 (started automatically on boot). Access a single unit at: `http://fishcam01.local:5000/`

### Verify Setup

```bash
bash verify_fishcam.sh
```

Auto-fixes missing packages, cron job, outdated repo, permissions. Reports hostname format, I2C config, SSH status, filesystem expansion.

---

## Output Data

### Video Files

**Location**: `../data/video/`

**Naming Convention**:
```
[iteration]_[hostname]_[timestamp]_[width]x[height]_awbm-[awb]_aem-[ae]_fr-[fps]_q-[quality]_sh-[sharp]_b-[bright]_c-[contrast]_ag-[gain]_sat-[sat].[format]
```

**Example**: `1_fishcam01_20250102T143052.123456Z_1920x1080_awbm-0_aem-0_fr-10_q-medium_sh-1.0_b-0.0_c-1.0_ag-8.0_sat-1.0.h264`

### Frame Metadata Files (JSON)

Written alongside each video file with `_metadata.json` suffix.

```json
{
  "video_file": "...",
  "start_time": "2025-01-02T14:30:52.123456",
  "duration_sec": 300,
  "expected_frame_rate": 10,
  "resolution": [1920, 1080],
  "total_frames": 2998,
  "frames": [
    {
      "frame_sequence": 0,
      "sensor_timestamp_us": 1234567890123,
      "system_time": 1735831852.123,
      "datetime": "2025-01-02T14:30:52.123456+0000",
      "exposure_time": 33000,
      "analogue_gain": 8.0
    }
  ]
}
```

- **`frame_sequence`**: Hardware frame sequence number (gaps = dropped frames).
- **`sensor_timestamp_us`**: Hardware timestamp from camera sensor (microseconds).
- **`system_time`**: Unix timestamp (seconds since epoch).
- **`datetime`**: ISO 8601 timestamp with timezone.

### IMU Data Files (CSV)

**Location**: `../data/imu/`

CSV rows with timestamp, quaternion (i, j, k, real), Euler angles (heading, pitch, roll), and enabled sensor reports. Written at the configured sample rate.

### Log Files

**Location**: `../data/logs/`

| Log File | Contents |
|----------|----------|
| `YYYYMMDDTHHMMSS.log` | Video capture events, frame statistics, buzzer events |
| `power_saving.log` | Power mode transitions, WiFi/BT/CPU changes, reed switch state |
| `imu_acquisition.log` | IMU start/stop, I2C errors, recovery attempts |
| `buzzer.log` | Trigger events, sequence timing, missed triggers |

---

## Setting Up a New FishCam System

**Default credentials:**
- Username: `fishcam`
- Hostname: `fishcam0x` (replace x with the unit number)

**Important**: The FishCam ID is derived from the hostname at runtime, not from the config file. Always set the hostname correctly.

### One-Time Setup (Skip if using FishCam SD-card image)

1. **Install required software:**
   ```bash
   sudo apt update && sudo apt upgrade
   sudo apt install python3 cron git
   pip install flask
   pip install adafruit-blinka adafruit-circuitpython-bno08x
   ```

2. **Download repository:**
   ```bash
   cd /home/fishcam/Desktop/
   git clone https://github.com/xaviermouy/FishCam.git
   ```

3. **Configure Raspberry Pi** (via raspi-config):
   - Interfaces: Enable SSH, Enable I2C
   - Localization: Set timezone to UTC
   - System: Boot to CLI, change hostname, splash screen off
   - Advanced Options: Persistent logging

4. **Set up IMU (BNO085)**:
   - Lower I2C baud rate to 100 kHz in `/boot/firmware/config.txt`:
     ```
     dtparam=i2c_arm=on,i2c_arm_baudrate=100000
     ```
   - Verify: `sudo i2cdetect -y 1` (should show 0x4A)

5. **Setup cron job for auto-start:**
   ```bash
   crontab -e
   # Add: @reboot sh /home/fishcam/Desktop/FishCam/FishCam/scripts/fishcamStartup.sh &
   ```

6. **Fix folder ownership:**
   ```bash
   sudo chown -R fishcam:fishcam /home/fishcam/Desktop/FishCam/
   ```

See [fishcam_setup_steps.txt](FishCam/fishcam_setup_steps.txt) for the complete checklist.

---

### Per-FishCam Setup (Required for each unit)

1. **Update the repo**: `bash updateFishCamRepo.sh`

2. **Install WittyPi (v4 mini):**
   ```bash
   cd /home/fishcam/Desktop
   wget http://www.uugear.com/repo/WittyPi4/install.sh
   sudo sh install.sh
   sudo usermod -aG i2c fishcam
   sudo chown -R fishcam:fishcam /home/fishcam/Desktop/wittypi/
   ```

3. **Configure WittyPi**: `python configure_wittypi.py`

4. **Set hostname** (this becomes the FishCam ID):
   ```bash
   sudo raspi-config  # System > Change hostname to fishcam0x
   ```

5. **Set buzzer beep count** (legacy mode only): edit `buzzer.beep_count` in config to a unique value per unit.

6. **Configure WiFi credentials** in `fishcam_config.yaml`.

7. **Expand filesystem**: `sudo raspi-config` > Advanced Options > Expand Filesystem

8. **Adjust lens focus and camera orientation:**
   ```bash
   rpicam-hello --timeout 0 --width 1920 --height 1080 --framerate 10
   ```
   Set `vflip`/`hflip` in config as needed.

9. **Configure power saving mode** in `fishcam_config.yaml`. See [POWER_SAVING_SETUP.md](FishCam/POWER_SAVING_SETUP.md) for hardware wiring.

10. **Run pre-deployment wizard**: `python start_new_deployment.py`

11. **Physical checks**: coin battery, camera cable, O-rings, seal, pressure test.

---

### Pre-Deployment Checklist

- [ ] Run `python start_new_deployment.py` (covers most steps below)
- [ ] Verify video recording: `python run_video.py` (stop with Ctrl+C after one clip)
- [ ] Test buzzer: `python run_buzzer.py`
- [ ] Check IMU: `python monitor_imu.py`
- [ ] Run system check: `bash verify_fishcam.sh`
- [ ] Verify SD card has sufficient space
- [ ] Verify battery is fully charged
- [ ] External label matches hostname

---

## Power Saving and Battery Life

FishCam supports optional power saving mode for extended deployments. See [POWER_SAVING_SETUP.md](FishCam/POWER_SAVING_SETUP.md) for hardware setup.

**Control**: Reed switch + magnet toggles between deployment (power saving) and configuration (full power) modes.

| Configuration | Power Draw | Battery Life (10,000 mAh)* |
|--------------|------------|---------------------------|
| Video only (no power saving) | ~300-350 mA | ~28 hours |
| Video + High Endurance SD card | ~250-300 mA | ~33 hours |
| Video + Power Saving + High Endurance | ~150-200 mA | ~50-66 hours |
| Optimized (all features) | ~100-150 mA | ~66-100 hours |

*Assumes 80% usable capacity. Actual runtime varies with resolution, framerate, and conditions.

### Recommended SD Card: SanDisk High Endurance

- Optimized for continuous recording (designed for dashcams/security cameras)
- Lower power consumption (~50-100 mA vs ~150-200 mA for standard cards)
- Better write endurance (up to 10,000 hours continuous recording)
- Temperature rated (-25C to 85C)

---

## Multi-FishCam Deployment

For deploying multiple fishcams with m-sequence buzzer mode (recommended):

1. Use the same `fishcam_config.yaml` on all units (same `msequence_n`, `chip_duration_sec`, `trigger_times`).
2. Set each unit's hostname to a unique `fishcamXX` (e.g., fishcam01, fishcam02, ...). The m-sequence is automatically derived from the unit number.
3. All fishcams play unique sequences at the same trigger times, enabling TDOA cross-correlation.

For legacy beep mode, set `sequence_mode: 'beep'` and assign a unique `beep_count` per unit.
