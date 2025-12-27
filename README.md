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
