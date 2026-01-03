# FishCam - Autonomous Underwater Video Recording System

## Overview

FishCam is an autonomous underwater video recording system designed for long-term deployment in marine environments. This repository contains an **updated version** of the original FishCam design with support for newer Raspberry Pi libraries (Picamera2) and hardware.

**Original FishCam code**: https://github.com/xaviermouy/fishcam_2020_paper

---

## Scripts

### Main Scripts

- **`captureVideo.py`** - Main video capture script. Runs continuously, capturing videos and optionally triggering the buzzer based on `iteration_period`.

- **`runBuzzer.py`** - Buzzer control script. Plays beep sequences according to configuration. Can be run standalone or called by `captureVideo.py`.

- **`visualize_buzzer_sequences.py`** - Visualization tool to preview buzzer sequences before deployment. Shows timeline of when each fishcam beeps to verify no overlaps.

### Utility Modules

- **`config.py`** - Configuration management module. Loads and provides access to settings from `fishcam_config.yaml`.

- **`buzzer_utils.py`** - Shared buzzer calculation utilities used by both `runBuzzer.py` and `visualize_buzzer_sequences.py`.

---

## Configuration File: `fishcam_config.yaml`

### FishCam Settings

```yaml
fishcam:
  id: "fishcam01"
```

- **`id`**: Unique identifier for this FishCam unit. In auto mode, the numeric portion determines beep pattern (e.g., "fishcam01" → 1).

---

### Video Capture Settings

```yaml
video:
  duration: 300
  resolution: [1600, 1200]
  frameRate: 10
  quality: 'medium'
  format: 'h264'
```

- **`duration`**: Duration of each video file in seconds.
- **`resolution`**: Video resolution `[width, height]` in pixels.
- **`frameRate`**: Frame rate in frames per second.
- **`quality`**: Encoding quality. Options: `'very_low'`, `'low'`, `'medium'`, `'high'`, `'very_high'`.
- **`format`**: Video format. Options: `'h264'` or `'mjpeg'`.

---

### Camera Control Settings

```yaml
camera:
  # Image Quality
  sharpness: 1.0
  contrast: 1.0
  brightness: 0.0
  saturation: 1.0

  # Gain and Exposure
  AnalogueGain: 8.0
  AeEnable: true
  AeExposureMode: 0

  # White Balance
  AwbEnable: true
  AwbMode: 0

  # Image Orientation
  vflip: false
  hflip: false
```

- **`sharpness`**: Sharpness level (0.0 to 16.0).
- **`contrast`**: Contrast level (0.0 to 32.0).
- **`brightness`**: Brightness level (-1.0 to 1.0).
- **`saturation`**: Saturation level (0.0 to 32.0).
- **`AnalogueGain`**: Analogue gain (1.0 to 16.0, replaces ISO).
- **`AeEnable`**: Auto exposure enable (true/false).
- **`AeExposureMode`**: Auto exposure mode (0=Normal, 1=Short, 2=Long, 3=Custom).
- **`AwbEnable`**: Auto white balance enable (true/false).
- **`AwbMode`**: White balance mode (0=Auto, 1=Tungsten, 2=Fluorescent, 3=Indoor, 4=Daylight, 5=Cloudy, 6=Custom).
- **`vflip`**: Vertical flip (true/false).
- **`hflip`**: Horizontal flip (true/false).

---

### Buzzer Settings

```yaml
buzzer:
  enabled: true
  pin: 26
  mode: 'auto'
  iteration_period: -1

  # Common settings
  beep_duration_sec: 0.05
  beep_gap_sec: 0.1
  number_sequences: 5

  # Manual mode settings
  manual:
    beep_number: 2
    gap_between_sequences_sec: 5
    initial_delay_sec: 0

  # Auto mode settings
  auto:
    total_fishcams: 6
    base_beeps: 10
    safety_buffer_sec: 2
```

#### Common Settings

- **`enabled`**: Enable/disable buzzer functionality (true/false).
- **`pin`**: GPIO pin number for buzzer (BCM numbering).
- **`mode`**: Buzzer mode. Options: `'auto'` (sequential beeping for multi-fishcam deployments) or `'manual'` (custom configuration).
- **`iteration_period`**: How often buzzer runs during video capture. `-1` = once at startup only, `N` = every Nth video.
- **`beep_duration_sec`**: Duration of each individual beep in seconds.
- **`beep_gap_sec`**: Gap between beeps within a sequence in seconds.
- **`number_sequences`**: Number of times to repeat the full beep sequence.

#### Manual Mode Settings (`mode: 'manual'`)

- **`beep_number`**: Number of beeps per sequence.
- **`gap_between_sequences_sec`**: Gap between sequence repetitions in seconds.
- **`initial_delay_sec`**: Initial delay before starting beeping in seconds (0 = no delay).

#### Auto Mode Settings (`mode: 'auto'`)

- **`total_fishcams`**: Total number of fishcams being deployed together.
- **`base_beeps`**: Base number of beeps. Each fishcam gets `base_beeps + fishcam_number` beeps (e.g., FishCam 1 gets 11 beeps if `base_beeps: 10`).
- **`safety_buffer_sec`**: Safety buffer in seconds added to initial delays to account for clock drift between units.

**Auto mode behavior**: Fishcams beep sequentially (one after another) with automatically calculated delays to prevent overlap. Each fishcam has a unique number of beeps for identification.

---

### Power Saving Mode Settings

```yaml
power_saving:
  enabled: false
  reed_switch_pin: 18
  led_pin: 23
  check_interval: 2.0

  # Audio feedback when in configuration mode
  beep_in_config_mode: false
  beep_interval: 10.0
  beep_duration: 0.1

  # Component-specific power saving controls
  components:
    disable_wifi: true
    disable_bluetooth: true
    disable_hdmi: true
    disable_usb: true
    throttle_cpu: true
    stop_services: true
    disable_led_triggers: true
```

#### Main Settings

- **`enabled`**: Enable/disable power saving mode (true/false). Requires reed switch hardware. Set to false for FishCams without reed switch.
- **`reed_switch_pin`**: GPIO pin number for reed switch (BCM numbering). Default: 18 (Pin 12, right side of Pi).
- **`led_pin`**: GPIO pin number for status LED (BCM numbering). Default: 23 (Pin 16, right side of Pi).
- **`check_interval`**: How often to check reed switch state in seconds. Default: 2.0 seconds.

#### Audio Feedback Settings

- **`beep_in_config_mode`**: Enable/disable periodic beeps when magnet is near (configuration mode). Default: false.
- **`beep_interval`**: Interval between beeps in seconds when in configuration mode. Default: 10.0 seconds.
- **`beep_duration`**: Duration of each beep in seconds. Default: 0.1 seconds.

**Note**: Buzzer beep feature requires buzzer hardware to be enabled in `buzzer` settings. The buzzer GPIO pin is taken from the `buzzer.pin` setting.

#### Component-Specific Power Saving Controls

Each power saving feature can be individually enabled or disabled. Set to `true` to enable power saving for that component, `false` to keep it always on.

- **`disable_wifi`**: Disable WiFi in power saving mode. Saves ~40-50 mA. Default: true.
- **`disable_bluetooth`**: Disable Bluetooth in power saving mode. Saves ~10-15 mA. Default: true.
- **`disable_hdmi`**: Disable HDMI output in power saving mode. Saves ~20-30 mA. Default: true.
- **`disable_usb`**: Enable USB autosuspend in power saving mode. Saves ~20-30 mA. Default: true (safe for most Pi camera modules).
- **`throttle_cpu`**: Throttle CPU frequency (1000 MHz → 600 MHz) in power saving mode. Saves ~50-100 mA. Default: true.
- **`stop_services`**: Stop non-essential services in power saving mode. Saves ~10-20 mA. Default: true.
- **`disable_led_triggers`**: Disable activity LED triggers in power saving mode. Minimal savings. Default: true.

**Example - WiFi always on (for SSH access during deployment):**
```yaml
components:
  disable_wifi: false  # Keep WiFi on even in power saving mode
  disable_bluetooth: true
  disable_hdmi: true
  # ... other settings
```

**See [POWER_SAVING_SETUP.md](POWER_SAVING_SETUP.md) for complete hardware setup and usage instructions.**

---

### File Paths

```yaml
paths:
  output_dir: '../data'
  log_dir: '../logs'
  iterator_file: 'iterator.config'
  config_file: 'fishcam_config.yaml'
```

- **`output_dir`**: Directory for video files.
- **`log_dir`**: Directory for log files.
- **`iterator_file`**: Filename for iteration counter.
- **`config_file`**: Name of this configuration file.

---

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install pyyaml picamera2 lgpio matplotlib numpy
   ```

2. **Edit configuration**: Modify `fishcam_config.yaml` with your settings.

3. **Test buzzer configuration** (optional but recommended):
   ```bash
   python visualize_buzzer_sequences.py
   ```

4. **Run the system**:
   ```bash
   python captureVideo.py
   ```

---

## Usage Examples

### Visualize Buzzer Sequences

```bash
# Use settings from fishcam_config.yaml
python visualize_buzzer_sequences.py

# Save visualization to file
python visualize_buzzer_sequences.py --output timeline.png

# Limit display duration to 60 seconds
python visualize_buzzer_sequences.py --duration 60
```

### Run Buzzer Standalone

```bash
python runBuzzer.py
```

---

## Output Data

FishCam generates three types of output files during operation:

### Log Files

**Location**: `../logs/` (configured in `paths.log_dir`)

#### Main Video Capture Log

**Naming**: `YYYYMMDDTHHMMSS.log` (e.g., `20250102T143052.log`)

**Contents**:
- Video acquisition start/stop events
- Video filenames and settings
- Buzzer operation events (when enabled)
- Frame statistics (expected vs actual frames, dropped frames, sequence gaps)
- Warnings for significant frame loss (>5% dropped)
- Error messages and exceptions

**Example log entries**:
```
2025-01-02 14:30:52,123 INFO Video acquisition started
2025-01-02 14:30:52,125 INFO FishCam ID: fishcam01
2025-01-02 14:30:54,200 INFO Buzzer turned ON
2025-01-02 14:35:52,456 INFO Frame metadata saved: 1_fishcam01_20250102T143052.123456Z_1600x1200_metadata.json
2025-01-02 14:35:52,457 INFO Frame stats: Expected=3000, Actual=2998, Dropped=2, Sequence_gaps=1
```

#### Power Saving Mode Log

**Naming**: `power_saving.log`

**Contents** (when power saving mode is enabled):
- Power saving controller startup/shutdown
- Mode transitions (power saving ↔ configuration)
- Reed switch state changes
- GPIO initialization and configuration
- WiFi/Bluetooth enable/disable operations
- CPU frequency changes
- Service start/stop operations
- Buzzer beep events (when `beep_in_config_mode` enabled)
- Error messages and warnings

**Example log entries**:
```
2025-01-02 14:30:45,000 INFO ============================================================
2025-01-02 14:30:45,001 INFO FishCam Power Saving Mode Controller
2025-01-02 14:30:45,002 INFO ============================================================
2025-01-02 14:30:45,010 INFO Power saving mode is ENABLED
2025-01-02 14:30:45,011 INFO Reed switch on GPIO 18
2025-01-02 14:30:45,012 INFO Status LED on GPIO 23
2025-01-02 14:30:45,013 INFO Config mode beeping ENABLED (interval: 10.0s, duration: 0.1s)
2025-01-02 14:30:45,020 INFO GPIO initialized: Reed switch on GPIO18, LED on GPIO23, Buzzer on GPIO26
2025-01-02 14:30:45,025 INFO Reed switch not activated - entering power saving mode
2025-01-02 14:30:45,030 INFO Entering power saving mode...
2025-01-02 14:30:45,035 INFO Disabling WiFi...
2025-01-02 14:30:45,250 INFO Disabling Bluetooth...
2025-01-02 14:30:45,450 INFO Power saving mode activated
2025-01-02 14:45:12,100 INFO Magnet detected - switching to config mode
2025-01-02 14:45:12,105 INFO Entering configuration mode...
2025-01-02 14:45:12,110 INFO Enabling WiFi...
2025-01-02 14:45:12,350 INFO Configuration mode activated
```

#### Power Saving Startup Log

**Naming**: `power_saving_startup.log`

**Contents**: Startup output from power saving controller when launched by `camStartup.sh`. Useful for debugging boot issues.

### Video Files

**Location**: `../data/[iteration_number]/` (configured in `paths.output_dir`)

**Naming Convention**:
```
[iteration]_[fishcam_id]_[timestamp]_[width]x[height]_awbm-[awb_mode]_aem-[ae_mode]_fr-[framerate]_q-[quality]_sh-[sharpness]_b-[brightness]_c-[contrast]_ag-[analogue_gain]_sat-[saturation].[format]
```

**Example**: `1_fishcam01_20250102T143052.123456Z_1600x1200_awbm-0_aem-0_fr-10_q-medium_sh-1.0_b-0.0_c-1.0_ag-8.0_sat-1.0.h264`

**Format**: H.264 (`.h264`) or Motion JPEG (`.mjpeg`) based on `video.format` setting

**Settings Encoded in Filename**:
- `awbm`: Auto White Balance Mode
- `aem`: Auto Exposure Mode
- `fr`: Frame rate (fps)
- `q`: Quality level
- `sh`: Sharpness
- `b`: Brightness
- `c`: Contrast
- `ag`: Analogue Gain
- `sat`: Saturation

### Frame Metadata Files (JSON)

**Location**: Same directory as video files

**Naming**: Same as video file but with `_metadata.json` suffix

**Example**: `1_fishcam01_20250102T143052.123456Z_1600x1200_awbm-0_aem-0_fr-10_q-medium_sh-1.0_b-0.0_c-1.0_ag-8.0_sat-1.0_metadata.json`

**Purpose**:
- Accurate frame-level timestamps for each captured frame
- Detection and quantification of dropped frames
- Synchronization across multiple FishCam units
- Post-processing and frame extraction

**JSON Structure**:
```json
{
  "video_file": "1_fishcam01_20250102T143052.123456Z_1600x1200_..._metadata.json",
  "start_time": "2025-01-02T14:30:52.123456",
  "duration_sec": 300,
  "expected_frame_rate": 10,
  "resolution": [1600, 1200],
  "total_frames": 2998,
  "frames": [
    {
      "frame_sequence": 0,
      "sensor_timestamp_us": 1234567890123,
      "system_time": 1735831852.123,
      "datetime": "2025-01-02T14:30:52.123456+0000",
      "exposure_time": 33000,
      "analogue_gain": 8.0
    },
    ...
  ]
}
```

**Frame Metadata Fields**:
- `frame_sequence`: Hardware frame sequence number (gaps indicate dropped frames)
- `sensor_timestamp_us`: Hardware timestamp from camera sensor (microseconds)
- `system_time`: Unix timestamp (seconds since epoch)
- `datetime`: Human-readable timestamp with timezone (ISO 8601 format)
- `exposure_time`: Exposure time in microseconds
- `analogue_gain`: Analogue gain value used for this frame

**Use Cases**:
- **Dropped Frame Detection**: Compare `expected_frame_rate × duration_sec` with `total_frames`
- **Accurate Timing**: Use `sensor_timestamp_us` for precise frame timing
- **Multi-Camera Sync**: Use `datetime` to synchronize footage across multiple FishCams
- **Frame Extraction**: Use `frame_sequence` to extract specific frames from video

---

## Power Saving and Battery Life Optimization

FishCam supports an optional power saving mode for extended underwater deployments. Proper hardware selection and configuration can extend battery life by 40-60%.

### Power Saving Mode

**Optional reed switch-controlled power management** - See [POWER_SAVING_SETUP.md](POWER_SAVING_SETUP.md) for detailed setup.

**Features:**
- WiFi/Bluetooth disabled during deployment
- HDMI output disabled
- CPU frequency throttled (1000 MHz → 600 MHz)
- USB autosuspend enabled (optional)
- Non-essential services stopped

**Control:**
- Reed switch + magnet: Toggle between deployment and configuration modes
- Status LED: Visual indication (optional)
- Buzzer beep: Audio feedback in config mode (optional)

**Power Savings:**

| Component | Power Saving Mode | Normal Mode | Savings |
|-----------|------------------|-------------|---------|
| WiFi | Disabled | Enabled | ~40-50 mA |
| Bluetooth | Disabled | Enabled | ~10-15 mA |
| HDMI | Disabled | Enabled | ~20-30 mA |
| CPU (throttled) | 600 MHz | 1000 MHz | ~50-100 mA |
| USB (optional) | Autosuspend | Always On | ~20-30 mA |
| Services | Stopped | Running | ~10-20 mA |
| **Total Savings** | | | **~150-245 mA** |

**Battery Life Impact:**
- Typical video recording: ~250-300 mA
- With power saving: ~100-150 mA reduction
- **Result: 40-60% longer deployment time**

### MicroSD Card Selection (Critical for Power Consumption)

**MicroSD card choice significantly impacts power consumption and reliability.**

#### Recommended: SanDisk High Endurance

**Why SanDisk High Endurance:**
- **Optimized for continuous recording** (designed for dashcams/security cameras)
- **Lower power consumption** (~50-100 mA vs ~150-200 mA for standard cards)
- **Better write endurance** (up to 10,000 hours continuous recording)
- **More consistent performance** (reduces CPU overhead from waiting on slow writes)
- **Temperature rated** (-25°C to 85°C - suitable for underwater deployments)

**Power Impact Example:**
- Standard microSD: ~150-200 mA during writes
- High Endurance: ~50-100 mA during writes
- **Savings: ~50-100 mA** (significant for battery-powered deployments)

**Recommended Sizes:**
- 64 GB: ~7 hours at 1600×1200, 10 fps, H.264 medium quality
- 128 GB: ~14 hours
- 256 GB: ~28 hours

#### Alternative: Industrial MicroSD Cards

**Industrial-grade cards** (e.g., SanDisk Industrial, Samsung Industrial):
- **Pros**: Higher endurance, wider temperature range, better reliability
- **Cons**: 2-3× more expensive than High Endurance
- **When to use**: Critical deployments, extreme environments, multi-week missions

**Avoid:**
- ❌ Standard consumer microSD cards (high power, low endurance)
- ❌ Ultra-high-speed cards (UHS-II/UHS-III) - unnecessary speed, higher power
- ❌ Unknown/cheap brands - unreliable performance and power characteristics

### Total Power Consumption Estimates

**Typical FishCam Power Budget:**

| Configuration | Power Draw | Example Battery Life* |
|--------------|------------|---------------------|
| **Video only (no power saving)** | ~300-350 mA | 10,000 mAh → ~28 hours |
| **Video + High Endurance card** | ~250-300 mA | 10,000 mAh → ~33 hours |
| **Video + Power Saving + High Endurance** | ~150-200 mA | 10,000 mAh → ~50-66 hours |
| **Optimized (all features)** | ~100-150 mA | 10,000 mAh → ~66-100 hours |

*Battery life estimates assume 10,000 mAh battery pack with 80% usable capacity. Actual runtime varies with resolution, framerate, and environmental conditions.

### Power Optimization Checklist

For maximum deployment duration:

- [ ] Use **SanDisk High Endurance** microSD card (or industrial grade)
- [ ] Enable **power saving mode** with reed switch (see [POWER_SAVING_SETUP.md](POWER_SAVING_SETUP.md))
- [ ] Set appropriate **video resolution** (1600×1200 recommended for Pi Zero 2W)
- [ ] Use **H.264 encoding** (more efficient than MJPEG)
- [ ] Set **quality: 'medium'** or 'low' (reduces encoding CPU load)
- [ ] Disable **WiFi/Bluetooth** during deployment (power saving mode does this automatically)
- [ ] Use **high-capacity battery** (10,000+ mAh recommended)
- [ ] Ensure **good SD card** (Class 10 or UHS-I minimum for High Endurance)

**See [POWER_SAVING_SETUP.md](POWER_SAVING_SETUP.md) for complete power saving mode setup instructions.**

---

## Multi-FishCam Deployment

For deploying multiple fishcams, use `mode: 'auto'`:

1. Set the same configuration on all units:
   ```yaml
   buzzer:
     mode: 'auto'
     auto:
       total_fishcams: 6
       base_beeps: 10
   ```

2. Change only the `fishcam.id` on each unit: `fishcam01`, `fishcam02`, `fishcam03`, etc.

3. All fishcams will automatically beep sequentially with unique patterns (11, 12, 13... beeps).

---

## Setting Up a New FishCam System

**Default credentials:**
- Username: `fishcam`
- Hostname: `fishcam0x` (replace x with the fishcam number)

### One-Time Setup (Skip if using FishCam SD-card image)

These steps are already done when using the FishCam SD-card image:

- [ ] **Turn off Bluetooth** (to save power)

- [ ] **Install required software:**
  ```bash
  sudo apt update
  sudo apt upgrade
  sudo apt install python3
  sudo apt install cron
  sudo apt install git
  ```

- [ ] **Download GitHub repository:**
  ```bash
  cd /home/fishcam/Desktop/
  git clone https://github.com/xaviermouy/FishCam.git
  ```

- [ ] **Configure system settings:**
  - Open control center
  - Interfaces → Enable SSH
  - Localization → Set timezone to UTC
  - System → Boot to CLI
  - System → Change hostname to `fishcam01`
  - System → Splash screen off

- [ ] **Setup cron job for auto-start:**
  ```bash
  crontab -e
  # Add this line:
  @reboot sh /home/fishcam/Desktop/FishCam/FishCam/scripts/camStartup.sh &
  ```
  - Save: `Ctrl+O`, then `Enter`
  - Exit: `Ctrl+X`
  - Verify: `sudo crontab -l`

- [ ] **Mark fishcam number on SD card** (with permanent marker)

---

### Per-FishCam Setup (Required for each unit)

Complete these steps for **every FishCam**, even when using the FishCam SD-card image:

- [ ] **Install WittyPi (v4 mini):**
  ```bash
  cd /home/fishcam/Desktop
  wget http://www.uugear.com/repo/WittyPi4/install.sh
  sudo sh install.sh
  ```

- [ ] **Configure WittyPi:**
  ```bash
  sudo sh /home/fishcam/Desktop/wittypi/wittyPi.sh
  ```
  - Synchronize network time
  - View/change other settings → Default state when powered: **ON**

- [ ] **Change hostname:**
  - Open control center → System → Change hostname to `fishcam0x` (replace x with fishcam number)

- [ ] **Update FishCam ID in configuration:**
  ```bash
  nano /home/fishcam/Desktop/FishCam/FishCam/scripts/fishcam_config.yaml
  ```
  - Change `fishcam: id:` to `"fishcam0x"` (replace x with fishcam number)

- [ ] **Verify buzzer configuration:**
  - Edit `fishcam_config.yaml`
  - Ensure `mode: 'auto'` and fields in `auto:` section are correct
  - Verify `total_fishcams` matches your deployment

- [ ] **Expand filesystem:**
  ```bash
  sudo raspi-config
  # Select: Advanced Options → Expand Filesystem
  ```

- [ ] **Adjust camera lens focus:**
  ```bash
  rpicam-hello --timeout 0
  ```
  - Physically adjust lens while viewing preview
  - Press `Ctrl+C` to exit when done

- [ ] **Adjust camera orientation:**
  ```bash
  rpicam-hello --timeout 0
  ```
  - Test camera orientation
  - Adjust `vflip` and `hflip` in `fishcam_config.yaml` if needed
  - Add colored tape to chassis and bottle to indicate "up" side

- [ ] **Label the chassis** with "fishcam0x"

- [ ] **Install coin battery** on the board (for real-time clock)

- [ ] **Close the bottle/housing**

- [ ] **Pressure test:** Test that bottle is sealed properly using pump

---

### Pre-Deployment Checklist

Before deploying:

- [ ] Test video recording: `python captureVideo.py` (stop with `Ctrl+C` after one video)
- [ ] Test buzzer: `python runBuzzer.py`
- [ ] Visualize buzzer sequences: `python visualize_buzzer_sequences.py`
- [ ] Check logs in `../logs/` for any errors
- [ ] Verify SD card has sufficient space
- [ ] Verify battery is fully charged
- [ ] External label on housing matches `fishcam.id` in config
