#!/usr/bin/env python3
"""
FishCam Power Saving Mode Controller

This script monitors a reed switch to toggle between power saving mode (deployment)
and configuration mode. When a magnet is brought near the reed switch, the system
enters configuration mode with full power. When removed, it enters power saving mode
to maximize battery life during underwater deployments.

Hardware (configurable in fishcam_config.yaml):
- Reed switch on GPIO 18 (default, Pin 12 - right side)
- Status LED on GPIO 23 (default, Pin 16 - right side)

Power Saving Mode (LED OFF):
- WiFi disabled
- Bluetooth disabled
- HDMI output disabled
- CPU frequency capped
- Non-essential services stopped

Configuration Mode (LED ON):
- Full power restored
- WiFi enabled
- HDMI enabled
- Normal CPU operation
"""

import lgpio
import time
import subprocess
import logging
import sys
import os
from pathlib import Path
import config

# State file to persist mode across reboots
STATE_FILE = '/tmp/fishcam_power_mode.state'


class PowerSavingController:
    def __init__(self, reed_pin, led_pin, check_interval, buzzer_pin=None,
                 beep_in_config_mode=False, beep_interval=10.0, beep_duration=0.1,
                 disable_wifi=True, disable_bluetooth=True, disable_hdmi=True,
                 disable_usb=False, throttle_cpu=True, stop_services=True,
                 disable_led_triggers=True):
        self.reed_pin = reed_pin
        self.led_pin = led_pin
        self.check_interval = check_interval
        self.buzzer_pin = buzzer_pin
        self.beep_in_config_mode = beep_in_config_mode
        self.beep_interval = beep_interval
        self.beep_duration = beep_duration

        # Component-specific power saving controls
        self.disable_wifi = disable_wifi
        self.disable_bluetooth = disable_bluetooth
        self.disable_hdmi = disable_hdmi
        self.disable_usb = disable_usb
        self.throttle_cpu = throttle_cpu
        self.stop_services = stop_services
        self.disable_led_triggers = disable_led_triggers

        self.gpio_handle = None
        self.current_mode = None  # 'config' or 'power_saving'
        self.last_beep_time = 0  # Track when last beep occurred

        # Initialize GPIO
        try:
            self.gpio_handle = lgpio.gpiochip_open(0)

            # Configure reed switch as input with pull-up
            # When magnet is near: switch closes, pin reads LOW (0)
            # When magnet is away: switch opens, pin reads HIGH (1)
            lgpio.gpio_claim_input(self.gpio_handle, self.reed_pin, lgpio.SET_PULL_UP)

            # Configure LED as output
            lgpio.gpio_claim_output(self.gpio_handle, self.led_pin)

            # Configure buzzer as output if provided
            if self.buzzer_pin is not None:
                lgpio.gpio_claim_output(self.gpio_handle, self.buzzer_pin)
                lgpio.gpio_write(self.gpio_handle, self.buzzer_pin, 0)  # Ensure buzzer is off
                logging.info(f"GPIO initialized: Reed switch on GPIO{self.reed_pin}, LED on GPIO{self.led_pin}, Buzzer on GPIO{self.buzzer_pin}")
            else:
                logging.info(f"GPIO initialized: Reed switch on GPIO{self.reed_pin}, LED on GPIO{self.led_pin}")
        except Exception as e:
            logging.error(f"Failed to initialize GPIO: {e}")
            raise

    def read_reed_switch(self):
        """
        Read reed switch state
        Returns True if magnet is near (config mode requested)
        """
        try:
            # Read pin: 0 = magnet near (switch closed), 1 = magnet away (switch open)
            pin_state = lgpio.gpio_read(self.gpio_handle, self.reed_pin)
            return pin_state == 0  # True when magnet is near
        except Exception as e:
            logging.error(f"Failed to read reed switch: {e}")
            return False

    def set_led(self, state):
        """Set LED state (True = ON, False = OFF)"""
        try:
            lgpio.gpio_write(self.gpio_handle, self.led_pin, 1 if state else 0)
        except Exception as e:
            logging.error(f"Failed to set LED: {e}")

    def beep(self, duration=None):
        """
        Sound buzzer for a short beep

        Args:
            duration: Beep duration in seconds (uses self.beep_duration if not specified)
        """
        if self.buzzer_pin is None:
            return  # No buzzer configured

        if duration is None:
            duration = self.beep_duration

        try:
            lgpio.gpio_write(self.gpio_handle, self.buzzer_pin, 1)  # Turn on
            time.sleep(duration)
            lgpio.gpio_write(self.gpio_handle, self.buzzer_pin, 0)  # Turn off
        except Exception as e:
            logging.error(f"Failed to beep buzzer: {e}")

    def run_command(self, command, check=False):
        """Execute shell command with error handling"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
            if result.returncode != 0 and result.stderr:
                logging.warning(f"Command '{command}' returned: {result.stderr.strip()}")
            return result.returncode == 0
        except Exception as e:
            logging.error(f"Failed to run command '{command}': {e}")
            return False

    def enter_power_saving_mode(self):
        """Enter power saving mode (deployment mode)"""
        if self.current_mode == 'power_saving':
            return  # Already in power saving mode

        logging.info("Entering power saving mode...")

        # Turn off LED
        self.set_led(False)

        # Disable WiFi (if enabled in config)
        if self.disable_wifi:
            logging.info("Disabling WiFi...")
            self.run_command("sudo rfkill block wifi")
        else:
            logging.info("WiFi disable skipped (disabled in config)")

        # Disable Bluetooth (if enabled in config)
        if self.disable_bluetooth:
            logging.info("Disabling Bluetooth...")
            self.run_command("sudo rfkill block bluetooth")
        else:
            logging.info("Bluetooth disable skipped (disabled in config)")

        # Disable HDMI output (if enabled in config)
        if self.disable_hdmi:
            logging.info("Disabling HDMI...")
            self.run_command("sudo tvservice -o")
        else:
            logging.info("HDMI disable skipped (disabled in config)")

        # Disable USB - enable aggressive USB autosuspend (if enabled in config)
        if self.disable_usb:
            logging.info("Disabling USB...")
            self.run_command("echo auto | sudo tee /sys/bus/usb/devices/usb1/power/control")
        else:
            logging.info("USB disable skipped (disabled in config)")

        # Throttle CPU (if enabled in config)
        if self.throttle_cpu:
            # Set CPU governor to powersave
            logging.info("Setting CPU to powersave mode...")
            for cpu in range(4):  # Pi Zero 2W has 4 cores
                self.run_command(f"echo powersave | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")

            # Cap CPU frequency to reduce power (1000 MHz -> 600 MHz)
            logging.info("Capping CPU frequency to 600 MHz...")
            for cpu in range(4):
                self.run_command(f"echo 600000 | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
        else:
            logging.info("CPU throttling skipped (disabled in config)")

        # Stop non-essential services (if enabled in config)
        if self.stop_services:
            logging.info("Stopping non-essential services...")
            services_to_stop = [
                'avahi-daemon',      # mDNS/DNS-SD
                'triggerhappy',      # Hotkey daemon
                'bluetooth',         # Bluetooth service
            ]
            for service in services_to_stop:
                self.run_command(f"sudo systemctl stop {service}")
        else:
            logging.info("Service stopping skipped (disabled in config)")

        # Disable LED triggers to save power (if enabled in config)
        if self.disable_led_triggers:
            self.run_command("echo none | sudo tee /sys/class/leds/led0/trigger")  # Activity LED
            self.run_command("echo none | sudo tee /sys/class/leds/led1/trigger")  # Power LED (if controllable)
        else:
            logging.info("LED trigger disable skipped (disabled in config)")

        self.current_mode = 'power_saving'
        self.save_state('power_saving')
        logging.info("Power saving mode activated")

    def enter_config_mode(self):
        """Enter configuration mode (full power)"""
        if self.current_mode == 'config':
            return  # Already in config mode

        logging.info("Entering configuration mode...")

        # Turn on LED
        self.set_led(True)

        # Enable WiFi (if it was disabled in power saving mode)
        if self.disable_wifi:
            logging.info("Enabling WiFi...")
            self.run_command("sudo rfkill unblock wifi")
        else:
            logging.info("WiFi enable skipped (was not disabled)")

        # Enable Bluetooth (if it was disabled in power saving mode)
        if self.disable_bluetooth:
            logging.info("Enabling Bluetooth...")
            self.run_command("sudo rfkill unblock bluetooth")
        else:
            logging.info("Bluetooth enable skipped (was not disabled)")

        # Enable HDMI output (if it was disabled in power saving mode)
        if self.disable_hdmi:
            logging.info("Enabling HDMI...")
            self.run_command("sudo tvservice -p")
            # Force HDMI mode
            self.run_command("sudo fbset -depth 8 && sudo fbset -depth 16")
        else:
            logging.info("HDMI enable skipped (was not disabled)")

        # Re-enable USB (if it was disabled in power saving mode)
        if self.disable_usb:
            logging.info("Enabling USB...")
            self.run_command("echo on | sudo tee /sys/bus/usb/devices/usb1/power/control")
        else:
            logging.info("USB enable skipped (was not disabled)")

        # Restore CPU performance (if it was throttled in power saving mode)
        if self.throttle_cpu:
            # Set CPU governor to ondemand (balanced performance)
            logging.info("Setting CPU to ondemand mode...")
            for cpu in range(4):
                self.run_command(f"echo ondemand | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")

            # Restore max CPU frequency
            logging.info("Restoring CPU frequency to 1000 MHz...")
            for cpu in range(4):
                self.run_command(f"echo 1000000 | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
        else:
            logging.info("CPU restore skipped (was not throttled)")

        # Start services (if they were stopped in power saving mode)
        if self.stop_services:
            logging.info("Starting services...")
            services_to_start = [
                'avahi-daemon',
                'triggerhappy',
                'bluetooth',
            ]
            for service in services_to_start:
                self.run_command(f"sudo systemctl start {service}")
        else:
            logging.info("Service starting skipped (were not stopped)")

        # Restore LED triggers (if they were disabled in power saving mode)
        if self.disable_led_triggers:
            self.run_command("echo mmc0 | sudo tee /sys/class/leds/led0/trigger")
        else:
            logging.info("LED trigger restore skipped (were not disabled)")

        self.current_mode = 'config'
        self.save_state('config')
        logging.info("Configuration mode activated")

    def save_state(self, state):
        """Save current state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                f.write(state)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def load_state(self):
        """Load saved state from file"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logging.error(f"Failed to load state: {e}")
        return 'power_saving'  # Default to power saving

    def run(self):
        """Main loop - monitor reed switch and manage power modes"""
        logging.info("Power saving controller started")

        # Load previous state or default to power saving
        saved_state = self.load_state()
        logging.info(f"Previous state: {saved_state}")

        # Initial state based on reed switch
        magnet_present = self.read_reed_switch()
        if magnet_present:
            logging.info("Reed switch activated at startup - entering config mode")
            self.enter_config_mode()
        else:
            logging.info("Reed switch not activated - entering power saving mode")
            self.enter_power_saving_mode()

        try:
            while True:
                # Check reed switch state
                magnet_present = self.read_reed_switch()

                if magnet_present:
                    # Magnet detected - enter config mode
                    if self.current_mode != 'config':
                        logging.info("Magnet detected - switching to config mode")
                        self.enter_config_mode()
                        # Reset beep timer when entering config mode
                        self.last_beep_time = time.time()
                else:
                    # No magnet - enter power saving mode
                    if self.current_mode != 'power_saving':
                        logging.info("Magnet removed - switching to power saving mode")
                        self.enter_power_saving_mode()

                # Periodic beep when in config mode (if enabled)
                if self.current_mode == 'config' and self.beep_in_config_mode:
                    current_time = time.time()
                    time_since_last_beep = current_time - self.last_beep_time

                    if time_since_last_beep >= self.beep_interval:
                        self.beep()
                        self.last_beep_time = current_time
                        logging.debug(f"Config mode beep (interval: {self.beep_interval}s)")

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logging.info("Shutting down power saving controller...")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up GPIO resources"""
        if self.gpio_handle is not None:
            try:
                lgpio.gpio_free(self.gpio_handle, self.reed_pin)
                lgpio.gpio_free(self.gpio_handle, self.led_pin)
                if self.buzzer_pin is not None:
                    # Ensure buzzer is off before cleanup
                    lgpio.gpio_write(self.gpio_handle, self.buzzer_pin, 0)
                    lgpio.gpio_free(self.gpio_handle, self.buzzer_pin)
                lgpio.gpiochip_close(self.gpio_handle)
                logging.info("GPIO cleaned up")
            except Exception as e:
                logging.error(f"Failed to clean up GPIO: {e}")


def main():
    # Setup logging
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'power_saving.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info("="*60)
    logging.info("FishCam Power Saving Mode Controller")
    logging.info("="*60)

    # Load power saving configuration
    try:
        power_saving_config = config.get_power_saving_settings()
        buzzer_config = config.get_buzzer_settings()
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Check if power saving is enabled
    if not power_saving_config['enabled']:
        logging.info("Power saving mode is DISABLED in configuration")
        logging.info("This FishCam will run without power saving features")
        logging.info("To enable: Set 'power_saving.enabled: true' in fishcam_config.yaml")
        sys.exit(0)  # Exit gracefully

    logging.info("Power saving mode is ENABLED")
    logging.info(f"Reed switch on GPIO {power_saving_config['reed_switch_pin']}")
    logging.info(f"Status LED on GPIO {power_saving_config['led_pin']}")
    logging.info(f"Check interval: {power_saving_config['check_interval']}s")

    # Get buzzer pin from buzzer config (if buzzer is enabled)
    buzzer_pin = None
    if buzzer_config.get('enabled', False):
        buzzer_pin = buzzer_config.get('pin', None)
        if buzzer_pin is not None:
            logging.info(f"Buzzer on GPIO {buzzer_pin}")

    # Log beep settings if enabled
    if power_saving_config['beep_in_config_mode']:
        if buzzer_pin is not None:
            logging.info(f"Config mode beeping ENABLED (interval: {power_saving_config['beep_interval']}s, duration: {power_saving_config['beep_duration']}s)")
        else:
            logging.warning("Config mode beeping ENABLED but buzzer not configured - beeping disabled")
    else:
        logging.info("Config mode beeping DISABLED")

    # Log component-specific power saving settings
    logging.info("Power saving components:")
    logging.info(f"  - WiFi disable: {power_saving_config['disable_wifi']}")
    logging.info(f"  - Bluetooth disable: {power_saving_config['disable_bluetooth']}")
    logging.info(f"  - HDMI disable: {power_saving_config['disable_hdmi']}")
    logging.info(f"  - USB autosuspend: {power_saving_config['disable_usb']}")
    logging.info(f"  - CPU throttling: {power_saving_config['throttle_cpu']}")
    logging.info(f"  - Stop services: {power_saving_config['stop_services']}")
    logging.info(f"  - Disable LED triggers: {power_saving_config['disable_led_triggers']}")

    # Check if running as root (required for some operations)
    if os.geteuid() != 0:
        logging.warning("Not running as root - some power saving features may not work")

    # Create and run controller with configuration
    controller = PowerSavingController(
        reed_pin=power_saving_config['reed_switch_pin'],
        led_pin=power_saving_config['led_pin'],
        check_interval=power_saving_config['check_interval'],
        buzzer_pin=buzzer_pin,
        beep_in_config_mode=power_saving_config['beep_in_config_mode'],
        beep_interval=power_saving_config['beep_interval'],
        beep_duration=power_saving_config['beep_duration'],
        # Component-specific controls
        disable_wifi=power_saving_config['disable_wifi'],
        disable_bluetooth=power_saving_config['disable_bluetooth'],
        disable_hdmi=power_saving_config['disable_hdmi'],
        disable_usb=power_saving_config['disable_usb'],
        throttle_cpu=power_saving_config['throttle_cpu'],
        stop_services=power_saving_config['stop_services'],
        disable_led_triggers=power_saving_config['disable_led_triggers']
    )
    controller.run()


if __name__ == '__main__':
    main()
