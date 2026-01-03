"""
FishCam Configuration Module

This module loads and manages configuration from fishcam_config.yaml
It provides easy access to configuration parameters for all FishCam scripts.
"""

import os
import sys
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
        """Get FishCam ID"""
        return self.config.get('fishcam', {}).get('id', 'FishCam_Unknown')

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

    def get_buzzer_settings(self):
        """
        Get buzzer settings as a dictionary

        Returns:
            dict: Buzzer settings (returns the full buzzer config structure)
        """
        buzzer = self.config.get('buzzer', {})

        # Return the full buzzer configuration including mode-specific settings
        return buzzer

    def get_paths(self):
        """
        Get file paths configuration

        Returns:
            dict: File paths
        """
        paths = self.config.get('paths', {})

        return {
            'output_dir': paths.get('output_dir', '../data'),
            'log_dir': paths.get('log_dir', '../logs'),
            'iterator_file': paths.get('iterator_file', 'iterator.config')
        }

    def get_power_saving_settings(self):
        """
        Get power saving mode settings

        Returns:
            dict: Power saving settings including component-specific controls
        """
        power_saving = self.config.get('power_saving', {})
        components = power_saving.get('components', {})

        return {
            'enabled': power_saving.get('enabled', False),
            'reed_switch_pin': power_saving.get('reed_switch_pin', 18),
            'led_pin': power_saving.get('led_pin', 23),
            'check_interval': power_saving.get('check_interval', 2.0),
            'beep_in_config_mode': power_saving.get('beep_in_config_mode', False),
            'beep_interval': power_saving.get('beep_interval', 10.0),
            'beep_duration': power_saving.get('beep_duration', 0.1),
            # Component-specific controls (default all to True for backward compatibility)
            'disable_wifi': components.get('disable_wifi', True),
            'disable_bluetooth': components.get('disable_bluetooth', True),
            'disable_hdmi': components.get('disable_hdmi', True),
            'disable_usb': components.get('disable_usb', False),  # Default False (safe)
            'throttle_cpu': components.get('throttle_cpu', True),
            'stop_services': components.get('stop_services', True),
            'disable_led_triggers': components.get('disable_led_triggers', True)
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

def get_power_saving_settings():
    """Get power saving mode settings from configuration"""
    return get_config().get_power_saving_settings()