#!/usr/bin/env python3
"""
FishCam Power Saving Mode Controller

This script monitors a magnetic latch switch (T092UA) to toggle between power saving
mode (deployment) and configuration mode. A brief pass of a magnet toggles the switch:
once ON it stays ON (config mode), once OFF it stays OFF (power saving mode).

Hardware (configurable in fishcam_config.yaml):
- Magnetic latch switch (T092UA) on GPIO 24 (default, Pin 18 - right side)
  Connect COM to GPIO 24 and NO to GND. Uses internal pull-up.
  Latched ON (contacts closed) = Config mode
  Latched OFF (contacts open)  = Power saving mode
- Red status LED on GPIO 23 (default, Pin 16 - right side)
  GPIO 23 → 220Ω → LED anode (+) → LED cathode (−) → GND

Power Saving Mode (LED flashes briefly once every 10 s):
- WiFi disabled
- Bluetooth disabled
- HDMI output disabled (configurable)
- CPU frequency capped
- Non-essential services stopped

Configuration Mode (LED solid ON):
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
import signal
import config


class PowerSavingController:
    CONFIG_LED_FLASH_INTERVAL = 10.0  # seconds between flashes in power saving mode
    CONFIG_LED_FLASH_DURATION = 0.1   # seconds the LED stays on per flash

    def __init__(self, reed_pin, led_pin, check_interval,
                 disable_wifi=True, disable_bluetooth=True, disable_hdmi=True,
                 disable_usb=False, throttle_cpu=True, stop_services=True,
                 disable_led_triggers=True, wifi_auto_connect=False,
                 wifi_ssid='', wifi_password='',
                 cpu_freq_power_saving=800, cpu_freq_config=1000):
        self.reed_pin = reed_pin
        self.led_pin = led_pin
        self.check_interval = check_interval
        self.shutdown_requested = False

        # Component-specific power saving controls
        self.disable_wifi = disable_wifi
        self.disable_bluetooth = disable_bluetooth
        self.disable_hdmi = disable_hdmi
        self.disable_usb = disable_usb
        self.throttle_cpu = throttle_cpu
        self.stop_services = stop_services
        self.disable_led_triggers = disable_led_triggers

        # WiFi auto-connect settings
        self.wifi_auto_connect = wifi_auto_connect
        self.wifi_ssid = wifi_ssid
        self.wifi_password = wifi_password

        # CPU frequency settings (in MHz)
        self.cpu_freq_power_saving = cpu_freq_power_saving
        self.cpu_freq_config = cpu_freq_config

        self.gpio_handle = None
        self.current_mode = None  # 'config' or 'power_saving'
        self._config_led_on = False       # tracks current config LED state to avoid redundant GPIO writes
        self._last_config_led_flash = 0.0 # timestamp of last config LED flash

        # Initialize GPIO
        try:
            self.gpio_handle = lgpio.gpiochip_open(0)

            # Configure latch switch as input with internal pull-up
            # Latched ON (contacts closed): pin reads LOW (0) = config mode
            # Latched OFF (contacts open):  pin reads HIGH (1) = power saving mode
            lgpio.gpio_claim_input(self.gpio_handle, self.reed_pin, lgpio.SET_PULL_UP)

            # Configure config LED as output
            lgpio.gpio_claim_output(self.gpio_handle, self.led_pin)

            logging.info(f"GPIO initialized: Latch switch on GPIO{self.reed_pin}, config LED on GPIO{self.led_pin}")
        except Exception as e:
            logging.error(f"Failed to initialize GPIO: {e}")
            # Cleanup GPIO handle on initialization failure
            if self.gpio_handle is not None:
                try:
                    lgpio.gpiochip_close(self.gpio_handle)
                except:
                    pass
                self.gpio_handle = None
            raise

    def read_latch_switch(self):
        """Read the latch switch state.

        Returns True if the switch is latched ON (contacts closed = config mode),
        False if latched OFF (contacts open = power saving mode).
        """
        try:
            # Internal pull-up: LOW (0) = contacts closed = ON, HIGH (1) = contacts open = OFF
            pin_state = lgpio.gpio_read(self.gpio_handle, self.reed_pin)
            return pin_state == 0
        except Exception as e:
            logging.error(f"Failed to read latch switch: {e}")
            return False

    def _set_config_led(self, state):
        """Low-level config LED GPIO write (True = ON, False = OFF).

        Tracks current state in _config_led_on to avoid redundant GPIO writes.
        """
        if state == self._config_led_on:
            return
        try:
            lgpio.gpio_write(self.gpio_handle, self.led_pin, 1 if state else 0)
            self._config_led_on = state
        except Exception as e:
            logging.error(f"Failed to set config LED: {e}")

    def update_config_led(self):
        """Drive the config mode LED based on current mode.

        Config mode  : solid ON
        Power saving : brief flash (CONFIG_LED_FLASH_DURATION s) once every
                       CONFIG_LED_FLASH_INTERVAL s
        """
        if self.current_mode == 'config':
            self._set_config_led(True)
        elif self.current_mode == 'power_saving':
            now = time.monotonic()
            if now - self._last_config_led_flash >= self.CONFIG_LED_FLASH_INTERVAL:
                self._set_config_led(True)
                time.sleep(self.CONFIG_LED_FLASH_DURATION)
                self._set_config_led(False)
                self._last_config_led_flash = now

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

    def _run_and_get_output(self, command):
        """Run a shell command and return its stdout, or None on failure."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout
            if result.stderr:
                logging.warning(f"Command '{command}' returned: {result.stderr.strip()}")
            return None
        except Exception as e:
            logging.error(f"Failed to run command '{command}': {e}")
            return None

    def service_exists(self, service_name):
        """Check if a systemd service exists"""
        try:
            result = subprocess.run(
                f"systemctl list-unit-files {service_name}.service",
                shell=True,
                capture_output=True,
                text=True
            )
            return service_name in result.stdout
        except Exception:
            return False

    def connect_wifi(self):
        """Connect to configured WiFi network"""
        if not self.wifi_auto_connect:
            return

        if not self.wifi_ssid or not self.wifi_password:
            logging.warning("WiFi auto-connect enabled but SSID or password not configured")
            return

        logging.info(f"Connecting to WiFi network: {self.wifi_ssid}")

        # Use nmcli to connect to WiFi with explicit security type
        # This will add the network if it doesn't exist, or connect if it does
        result = self.run_command(
            f"nmcli device wifi connect \"{self.wifi_ssid}\" password \"{self.wifi_password}\" wpa-psk"
        )

        if result:
            logging.info(f"Successfully connected to {self.wifi_ssid}")
        else:
            logging.warning(f"Failed to connect to {self.wifi_ssid}")

    def enter_power_saving_mode(self):
        """Enter power saving mode (deployment mode)"""
        if self.current_mode == 'power_saving':
            return  # Already in power saving mode

        logging.info("Entering power saving mode...")

        self._last_config_led_flash = 0.0  # trigger immediate flash on next update_config_led() call

        # Disable WiFi (if enabled in config)
        if self.disable_wifi:
            logging.info("Disabling WiFi...")
            # Use nmcli instead of rfkill to properly work with NetworkManager
            # Retry loop to fight NetworkManager auto-connect at boot
            max_attempts = 15
            retry_interval = 1.0
            for attempt in range(max_attempts):
                self.run_command("nmcli radio wifi off")
                time.sleep(retry_interval)

                # Check if WiFi is actually off
                output = self._run_and_get_output("nmcli radio wifi")
                if output is not None and "disabled" in output.lower():
                    logging.info(f"WiFi successfully disabled (attempt {attempt + 1}/{max_attempts})")
                    break
                elif attempt < max_attempts - 1:
                    logging.info(f"WiFi still enabled, retrying... (attempt {attempt + 1}/{max_attempts})")
                else:
                    logging.warning(f"WiFi may still be enabled after {max_attempts} attempts")
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
                # Check if cpufreq interface exists for this CPU
                if os.path.exists(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"):
                    self.run_command(f"echo powersave | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
                elif cpu == 0:
                    logging.warning(f"CPU frequency scaling not available on this system")
                    break

            # Cap CPU frequency to reduce power
            freq_khz = self.cpu_freq_power_saving * 1000  # Convert MHz to kHz
            logging.info(f"Capping CPU frequency to {self.cpu_freq_power_saving} MHz...")
            for cpu in range(4):
                if os.path.exists(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq"):
                    self.run_command(f"echo {freq_khz} | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
                elif cpu == 0:
                    logging.warning(f"CPU frequency capping not available on this system")
                    break
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
                if self.service_exists(service):
                    self.run_command(f"sudo systemctl stop {service}")
                else:
                    logging.info(f"Service '{service}' not found, skipping...")
        else:
            logging.info("Service stopping skipped (disabled in config)")

        # Disable LED triggers to save power (if enabled in config)
        if self.disable_led_triggers:
            self.run_command("echo none | sudo tee /sys/class/leds/led0/trigger")  # Activity LED
            self.run_command("echo none | sudo tee /sys/class/leds/led1/trigger")  # Power LED (if controllable)
        else:
            logging.info("LED trigger disable skipped (disabled in config)")

        self.current_mode = 'power_saving'
        logging.info("Power saving mode activated")

    def enter_config_mode(self):
        """Enter configuration mode (full power)"""
        if self.current_mode == 'config':
            return  # Already in config mode

        logging.info("Entering configuration mode...")

        # Enable WiFi (if it was disabled in power saving mode)
        if self.disable_wifi:
            logging.info("Enabling WiFi...")
            # Use nmcli instead of rfkill to properly work with NetworkManager
            self.run_command("nmcli radio wifi on")
            # Wait for WiFi to initialize before attempting connection
            time.sleep(3)
            # Auto-connect to configured network
            self.connect_wifi()
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
                if os.path.exists(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"):
                    self.run_command(f"echo ondemand | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
                elif cpu == 0:
                    logging.warning(f"CPU frequency scaling not available on this system")
                    break

            # Restore max CPU frequency
            freq_khz = self.cpu_freq_config * 1000  # Convert MHz to kHz
            logging.info(f"Restoring CPU frequency to {self.cpu_freq_config} MHz...")
            for cpu in range(4):
                if os.path.exists(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq"):
                    self.run_command(f"echo {freq_khz} | sudo tee /sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
                elif cpu == 0:
                    logging.warning(f"CPU frequency capping not available on this system")
                    break
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
                if self.service_exists(service):
                    self.run_command(f"sudo systemctl start {service}")
                else:
                    logging.info(f"Service '{service}' not found, skipping...")
        else:
            logging.info("Service starting skipped (were not stopped)")

        # Restore LED triggers (if they were disabled in power saving mode)
        if self.disable_led_triggers:
            self.run_command("echo mmc0 | sudo tee /sys/class/leds/led0/trigger")
        else:
            logging.info("LED trigger restore skipped (were not disabled)")

        self.current_mode = 'config'
        logging.info("Configuration mode activated")

    def run(self):
        """Main loop - monitor latch switch and manage power modes"""
        logging.info("Power saving controller started")

        try:
            # Set initial mode based on switch position at startup
            switch_on = self.read_latch_switch()
            if switch_on:
                logging.info("Latch switch ON at startup - entering config mode")
                self.enter_config_mode()
            else:
                logging.info("Latch switch OFF at startup - entering power saving mode")
                self.enter_power_saving_mode()
            self.update_config_led()

            while not self.shutdown_requested:
                switch_on = self.read_latch_switch()

                if switch_on:
                    if self.current_mode != 'config':
                        logging.info("Switch ON - switching to config mode")
                        self.enter_config_mode()
                else:
                    if self.current_mode != 'power_saving':
                        logging.info("Switch OFF - switching to power saving mode")
                        self.enter_power_saving_mode()

                self.update_config_led()

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
                self._set_config_led(False)
                lgpio.gpio_free(self.gpio_handle, self.reed_pin)
                lgpio.gpio_free(self.gpio_handle, self.led_pin)
                lgpio.gpiochip_close(self.gpio_handle)
                logging.info("GPIO cleaned up")
            except Exception as e:
                logging.error(f"Failed to clean up GPIO: {e}")

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logging.info(f"Received shutdown signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True


def main():
    # Setup logging
    log_dir = Path(__file__).parent / config.get_paths()['log_dir']
    log_dir.mkdir(parents=True, exist_ok=True)
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
    logging.info(f"Latch switch on GPIO {power_saving_config['reed_switch_pin']}")
    logging.info(f"Status LED on GPIO {power_saving_config['led_pin']}")
    logging.info(f"Check interval: {power_saving_config['check_interval']}s")

    # Log WiFi auto-connect settings
    if power_saving_config['wifi_auto_connect']:
        logging.info(f"WiFi auto-connect ENABLED: {power_saving_config['wifi_ssid']}")
    else:
        logging.info("WiFi auto-connect DISABLED")

    # Log component-specific power saving settings
    logging.info("Power saving components:")
    logging.info(f"  - WiFi disable: {power_saving_config['disable_wifi']}")
    logging.info(f"  - Bluetooth disable: {power_saving_config['disable_bluetooth']}")
    logging.info(f"  - HDMI disable: {power_saving_config['disable_hdmi']}")
    logging.info(f"  - USB autosuspend: {power_saving_config['disable_usb']}")
    logging.info(f"  - CPU throttling: {power_saving_config['throttle_cpu']}")
    if power_saving_config['throttle_cpu']:
        logging.info(f"    Power saving freq: {power_saving_config['cpu_freq_power_saving']} MHz")
        logging.info(f"    Config mode freq: {power_saving_config['cpu_freq_config']} MHz")
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
        # Component-specific controls
        disable_wifi=power_saving_config['disable_wifi'],
        disable_bluetooth=power_saving_config['disable_bluetooth'],
        disable_hdmi=power_saving_config['disable_hdmi'],
        disable_usb=power_saving_config['disable_usb'],
        throttle_cpu=power_saving_config['throttle_cpu'],
        stop_services=power_saving_config['stop_services'],
        disable_led_triggers=power_saving_config['disable_led_triggers'],
        # WiFi auto-connect
        wifi_auto_connect=power_saving_config['wifi_auto_connect'],
        wifi_ssid=power_saving_config['wifi_ssid'],
        wifi_password=power_saving_config['wifi_password'],
        # CPU frequency settings
        cpu_freq_power_saving=power_saving_config['cpu_freq_power_saving'],
        cpu_freq_config=power_saving_config['cpu_freq_config']
    )
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, controller.signal_handler)
    signal.signal(signal.SIGINT, controller.signal_handler)
    logging.info("Signal handlers registered")
    
    controller.run()


if __name__ == '__main__':
    main()