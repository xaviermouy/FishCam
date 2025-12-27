# FishCam Configuration System

## Overview

The FishCam system uses a centralized YAML configuration file (`fishcam_config.yaml`) to manage all parameters across all scripts. This makes it easy to configure your FishCam system in one place.

## Files

- **`fishcam_config.yaml`**: Main configuration file with all parameters
- **`config.py`**: Configuration management module
- **`captureVideo.py`**: Video capture script (uses configuration)
- **`runBuzzer.py`**: Buzzer control script (uses configuration)

## Quick Start

1. **Edit the configuration file**: Open `fishcam_config.yaml` and modify the parameters as needed
2. **Run the scripts**: Both `captureVideo.py` and `runBuzzer.py` will automatically load settings from the YAML file

## Configuration File Structure

The configuration file is organized into sections:

### FishCam Settings
```yaml
fishcam:
  id: "FishCam_01"  # Unique identifier for this unit
```

### Video Capture Settings
```yaml
video:
  duration: 300  # Duration of each video in seconds
  resolution: [4056, 3040]  # [width, height] in pixels
  frameRate: 10  # Frames per second
  quality: 'very_high'  # very_low, low, medium, high, very_high
  format: 'h264'  # h264 or mjpeg
```

### Camera Control Settings
```yaml
camera:
  # Image quality
  sharpness: 1.0  # 0.0 to 16.0
  contrast: 1.0   # 0.0 to 32.0
  brightness: 0.0  # -1.0 to 1.0
  saturation: 1.0  # 0.0 to 32.0

  # Gain and exposure
  AnalogueGain: 8.0  # 1.0 to 16.0 (replaces ISO)
  AeEnable: true  # Auto exposure on/off
  AeExposureMode: 0  # 0=Normal, 1=Short, 2=Long, 3=Custom

  # White balance
  AwbEnable: true  # Auto white balance on/off
  AwbMode: 0  # 0=Auto, 1=Tungsten, 2=Fluorescent, 3=Indoor, 4=Daylight, 5=Cloudy, 6=Custom

  # Image orientation
  vflip: false
  hflip: false
```

### Buzzer Settings
```yaml
buzzer:
  pin: 26  # GPIO pin (BCM numbering)
  beep_duration_sec: 0.01
  beep_gap_sec: 0.5
  beep_number: 10
  number_sequences: 5
  gap_between_sequences_sec: 5
  enabled: true
  iteration_period: -1
```

### File Paths
```yaml
paths:
  output_dir: '../data'
  log_dir: '../logs'
  iterator_file: 'iterator.config'
```

## Using the Configuration in Your Scripts

If you want to create custom scripts that use the configuration:

```python
import config

# Get specific configuration sections
video_settings = config.get_video_settings()
buzzer_settings = config.get_buzzer_settings()
fishcam_id = config.get_fishcam_id()
paths = config.get_paths()

# Get individual values
duration = config.get_config().get('video', 'duration')
pin = config.get_config().get('buzzer', 'pin')
```

## Requirements

Install PyYAML:
```bash
pip install pyyaml
```

## Troubleshooting

**Error: "Configuration file not found"**
- Make sure `fishcam_config.yaml` is in the same directory as your scripts

**Error: "Error parsing YAML configuration file"**
- Check the YAML syntax - common issues:
  - Incorrect indentation (use spaces, not tabs)
  - Missing colons after keys
  - Unquoted strings with special characters

**Values not updating**
- Make sure you saved `fishcam_config.yaml` after editing
- Restart your script to load new values