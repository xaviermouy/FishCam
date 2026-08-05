"""
FishCam Configuration Module

This module loads and manages configuration from fishcam_config.yaml
It provides easy access to configuration parameters for all FishCam scripts.
"""

import os
import sys
import socket
from pathlib import Path

# Auto-install PyYAML if not present
try:
    import yaml
except ImportError:
    print("PyYAML not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml
    print("PyYAML installed successfully!")


class FishCamConfig:
    """Configuration manager for FishCam system"""

    def __init__(self, config_file='fishcam_config.yaml'):
        """
        Initialize configuration from YAML file

        Args:
            config_file: Path to the YAML configuration file
        """
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from YAML file"""
        config_path = Path(__file__).parent / self.config_file

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please create {self.config_file} in the script directory."
            )

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML configuration file: {e}")

    def get_fishcam_id(self):
        """Get FishCam ID from the Pi hostname."""
        return socket.gethostname()

    def get_video_settings(self):
        """
        Get video capture settings as a dictionary

        Returns:
            dict: Video settings compatible with captureVideo function
        """
        video = self.config.get('video', {})
        camera = self.config.get('camera', {})

        # Combine video and camera settings into the format expected by captureVideo
        settings = {
            'duration': video.get('duration', 300),
            'resolution': tuple(video.get('resolution', [4056, 3040])),
            'frameRate': video.get('frameRate', 10),
            'quality': video.get('quality', 'medium'),
            'format': video.get('format', 'h264'),
            'sharpness': camera.get('sharpness', 1.0),
            'contrast': camera.get('contrast', 1.0),
            'brightness': camera.get('brightness', 0.0),
            'saturation': camera.get('saturation', 1.0),
            'AnalogueGain': camera.get('AnalogueGain', 8.0),
            'AeEnable': camera.get('AeEnable', True),
            'AeExposureMode': camera.get('AeExposureMode', 0),
            'AwbEnable': camera.get('AwbEnable', True),
            'AwbMode': camera.get('AwbMode', 0),
            'vflip': camera.get('vflip', False),
            'hflip': camera.get('hflip', False)
        }

        return settings

    def get_fishcam_settings(self):
        """
        Get fishcam settings as a dictionary

        Returns:
            dict: FishCam settings
        """
        return self.config.get('fishcam', {})

    def get_timezone(self):
        """Get the deployment local timezone (IANA name).

        Reads from the top-level 'timezone' key. Falls back to
        wittypi.timezone for backward compatibility with older configs.
        """
        return (
            self.config.get('timezone')
            or self.config.get('wittypi', {}).get('timezone', 'UTC')
        )

    def get_wittypi_settings(self):
        """
        Get WittyPi settings.

        Returns:
            dict: Full WittyPi configuration including schedule, deployment window,
                  voltage thresholds, and power-cut delay.
        """
        wittypi = self.config.get('wittypi', {})
        deployment = wittypi.get('deployment', {})
        schedule   = wittypi.get('daily_schedule', {})
        return {
            'install_dir':          wittypi.get('install_dir', '/home/fishcam/wittypi'),
            'i2c_address':          wittypi.get('i2c_address', 0x08),
            'power_cut_delay_sec':  wittypi.get('power_cut_delay_sec', 60),
            'low_voltage_cutoff_v':       wittypi.get('low_voltage_cutoff_v', 0),
            'recovery_voltage_v':         wittypi.get('recovery_voltage_v', 0),
            'voltage_log_interval_min':      wittypi.get('voltage_log_interval_min', 10),
            'auto_sync_rtc_from_internet':   wittypi.get('auto_sync_rtc_from_internet', True),
            'auto_sync_rtc_from_gps':        wittypi.get('auto_sync_rtc_from_gps', False),
            'rtc_sync_min_interval_min':     wittypi.get('rtc_sync_min_interval_min', 15),
            'timezone':             self.get_timezone(),
            'deployment': {
                'start': deployment.get('start', ''),
                'end':   deployment.get('end',   ''),
            },
            'daily_schedule': {
                'anchor_time': schedule.get('anchor_time', '00:00'),
                'windows':     schedule.get('windows', []),
            },
        }

    def get_network_settings(self):
        """
        Get network / WiFi settings.

        Returns:
            dict: Network settings (wifi_auto_connect, wifi_ssid, wifi_password)
        """
        network = self.config.get('network', {})
        return {
            'wifi_auto_connect': network.get('wifi_auto_connect', False),
            'wifi_ssid':         network.get('wifi_ssid', ''),
            'wifi_password':     network.get('wifi_password', ''),
        }

    def get_buzzer_settings(self):
        """
        Get buzzer settings as a dictionary.

        Returns:
            dict: Full buzzer configuration section.
        """
        buzzer = self.config.get('buzzer', {})
        return {
            'enabled':                   buzzer.get('enabled', False),
            'pin':                       buzzer.get('pin', 26),
            'trigger_times':             buzzer.get('trigger_times', []),
            'beep_count':                buzzer.get('beep_count', 1),
            'beep_duration_sec':         buzzer.get('beep_duration_sec', 0.1),
            'beep_gap_sec':              buzzer.get('beep_gap_sec', 0.1),
            'number_sequences':          buzzer.get('number_sequences', 1),
            'gap_between_sequences_sec': buzzer.get('gap_between_sequences_sec', 5),
            'missed_trigger_grace_sec':  buzzer.get('missed_trigger_grace_sec', 60),
            'timezone':                  self.get_timezone(),
        }

    def get_paths(self):
        """
        Get file paths configuration

        Returns:
            dict: File paths
        """
        paths = self.config.get('paths', {})

        return {
            'video_dir': paths.get('video_dir', '../data/video'),
            'log_dir':   paths.get('log_dir',   '../data/logs'),
            'imu_dir':   paths.get('imu_dir',   '../data/imu'),
            'gps_dir':   paths.get('gps_dir',   '../data/gps'),
        }

    def get_power_saving_settings(self):
        """
        Get power saving mode settings.

        WiFi credentials are in get_network_settings(), not here.

        Returns:
            dict: Power saving settings including component-specific controls
        """
        power_saving = self.config.get('power_saving', {})
        components = power_saving.get('components', {})

        return {
            'enabled':              power_saving.get('enabled', False),
            'reed_switch_pin':      power_saving.get('reed_switch_pin', 18),
            'led_pin':              power_saving.get('led_pin', 23),
            'check_interval':       power_saving.get('check_interval', 2.0),
            # CPU frequency settings (in MHz)
            'cpu_freq_power_saving': power_saving.get('cpu_freq_power_saving', 800),
            'cpu_freq_config':       power_saving.get('cpu_freq_config', 1000),
            # Component-specific controls
            'disable_wifi':          components.get('disable_wifi', True),
            'disable_bluetooth':     components.get('disable_bluetooth', True),
            'disable_hdmi':          components.get('disable_hdmi', True),
            'disable_usb':           components.get('disable_usb', False),
            'throttle_cpu':          components.get('throttle_cpu', True),
            'stop_services':         components.get('stop_services', True),
            'disable_led_triggers':  components.get('disable_led_triggers', True),
        }

    def get_imu_settings(self):
        """
        Get IMU (BNO085) acquisition settings.

        Returns:
            dict: IMU settings including enabled flag, I2C address,
                  sample rate, and per-report enable flags.
        """
        imu = self.config.get('imu', {})
        reports = imu.get('reports', {})
        return {
            'enabled':              imu.get('enabled', False),
            'i2c_address':          imu.get('i2c_address', 0x4A),
            'sample_rate_hz':       imu.get('sample_rate_hz', 50),
            'accelerometer':        reports.get('accelerometer', True),
            'gyroscope':            reports.get('gyroscope', True),
            'magnetometer':         reports.get('magnetometer', True),
            'rotation_vector':      reports.get('rotation_vector', True),
            'linear_acceleration':  reports.get('linear_acceleration', True),
            'gravity':              reports.get('gravity', True),
        }

    def get(self, *keys, default=None):
        """
        Get a nested configuration value using dot notation or multiple keys

        Args:
            *keys: Keys to traverse the configuration dictionary
            default: Default value if key not found

        Returns:
            Configuration value or default

        Example:
            config.get('video', 'duration')
            config.get('camera', 'AeEnable')
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value


# Create a global configuration instance
_config = None

def get_config(config_file='fishcam_config.yaml'):
    """
    Get the global configuration instance (singleton pattern)

    Args:
        config_file: Path to configuration file (only used on first call)

    Returns:
        FishCamConfig: Configuration instance
    """
    global _config
    if _config is None:
        _config = FishCamConfig(config_file)
    return _config


# Convenience functions for common operations
def get_video_settings():
    """Get video settings from configuration"""
    return get_config().get_video_settings()

def get_timezone():
    """Get the deployment local timezone (IANA name)"""
    return get_config().get_timezone()

def get_buzzer_settings():
    """Get buzzer settings from configuration"""
    return get_config().get_buzzer_settings()

def get_fishcam_settings():
    """Get fishcam settings from configuration"""
    return get_config().get_fishcam_settings()

def get_fishcam_id():
    """Get FishCam ID from configuration"""
    return get_config().get_fishcam_id()

def get_paths():
    """Get file paths from configuration"""
    return get_config().get_paths()

def get_network_settings():
    """Get network / WiFi settings from configuration"""
    return get_config().get_network_settings()

def get_wittypi_settings():
    """Get WittyPi settings from configuration"""
    return get_config().get_wittypi_settings()

def get_power_saving_settings():
    """Get power saving mode settings from configuration"""
    return get_config().get_power_saving_settings()

def get_imu_settings():
    """Get IMU acquisition settings from configuration"""
    return get_config().get_imu_settings()