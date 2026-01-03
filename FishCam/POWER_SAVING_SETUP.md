# FishCam Power Saving Mode Setup

## Overview

The power saving mode controller automatically manages power consumption based on a reed switch. When deployed underwater (magnet removed), the system enters low-power mode. When configuring (magnet near switch), full power is restored.

**Modes:**
- **Power Saving (LED OFF, silent)**: WiFi off, HDMI off, CPU throttled, services stopped → Maximum battery life
- **Configuration (LED ON, optional beep)**: Full power, WiFi enabled, HDMI enabled, periodic beep every 10s (optional) → Easy configuration and testing

---

## Hardware Components Needed

1. **Reed switch** (normally open, NO type)
   - Example: MC-38 wired magnetic contact switch
   - Any reed switch rated for 3.3V will work

2. **LED** (any color, 3mm or 5mm)
   - Green or blue recommended for status indication

3. **Current-limiting resistor** for LED
   - 220Ω to 330Ω resistor (1/4W or 1/8W)

4. **Magnet**
   - Small neodymium magnet or magnet included with reed switch

5. **Wire** (22-26 AWG)

---

## GPIO Wiring Diagram

### Raspberry Pi Zero 2W GPIO Pinout Reference

```
         3V3  (1) (2)  5V
   GPIO2/SDA  (3) (4)  5V
   GPIO3/SCL  (5) (6)  GND
       GPIO4  (7) (8)  GPIO14/TXD
         GND  (9) (10) GPIO15/RXD
      GPIO17 (11) (12) GPIO18
      GPIO27 (13) (14) GND
      GPIO22 (15) (16) GPIO23
         3V3 (17) (18) GPIO24
      GPIO10 (19) (20) GND
       GPIO9 (21) (22) GPIO25
      GPIO11 (23) (24) GPIO8
         GND (25) (26) GPIO7
```

### Reed Switch Wiring

**Connection:**
```
Reed Switch Pin 1 ──────────────┐
                                ├───► GPIO 18 (Pin 12) - RIGHT SIDE
Reed Switch Pin 2 ──────────────┼───► GND (Pin 6, 14, or 20) - RIGHT SIDE
                                │
                        Internal Pull-up
                        (enabled in software)
```

**How it works:**
- Magnet **AWAY**: Switch open → GPIO 18 reads HIGH (1) → Power saving mode
- Magnet **NEAR**: Switch closed → GPIO 18 reads LOW (0) → Configuration mode

### LED Wiring

**Connection:**
```
GPIO 23 (Pin 16) ──┬── 220Ω Resistor ──┬── LED Anode (+, longer leg)
                   │                    │
                   │                    └── LED Cathode (-, shorter leg, flat edge)
                   │                         │
                   │                         └── GND (Pin 14 or 20) - RIGHT SIDE
```

**Polarity Check:**
- **Anode (+)**: Longer leg, connects to resistor
- **Cathode (-)**: Shorter leg, flat edge on LED housing, connects to GND

### Complete Wiring Schematic (Right Side Pins)

```
Raspberry Pi Zero 2W
┌─────────────────────────────┐
│                             │
│  (12) GPIO18 ────────┐      │  RIGHT SIDE
│                      │      │
│  (16) GPIO23 ────────┼───┐  │
│                      │   │  │
│  (14) GND ───────────┼───┼──┼─────┐
│                      │   │  │     │
└──────────────────────┼───┼──┘     │
                       │   │        │
                       │   │        │
    Reed Switch        │   │        │
    ┌─────────┐        │   │        │
    │    1    ├────────┘   │        │
    │         │            │        │
    │    2    ├────────────┘        │
    └─────────┘                     │
                                    │
                  ┌─────────────────┘
                  │
                  │     220Ω
                  │    ┌─┴─┐
    LED           │    │   │
    ─┬─           │    └─┬─┘
     │ Anode (+)  │      │
     ↓            │      │
     │ Cathode (-)│──────┘
    ─┴─           │
     │            │
     └────────────┘
```

---

## Installation Steps

### 1. Hardware Assembly

**Note:** Only complete this step if you want power saving mode. FishCams can operate without it.

1. **Solder reed switch wires:**
   - Connect one wire from reed switch pin 1 to GPIO 18 (Pin 12) - RIGHT SIDE
   - Connect one wire from reed switch pin 2 to GND (Pin 14) - RIGHT SIDE

2. **Solder LED circuit:**
   - Solder 220Ω resistor to LED anode (longer leg)
   - Connect resistor to GPIO 23 (Pin 16) - RIGHT SIDE
   - Connect LED cathode (shorter leg) to GND (Pin 14 or 20) - RIGHT SIDE

3. **Mount components:**
   - Mount reed switch on housing where magnet can be easily placed/removed
   - Mount LED in visible location (near opening or in transparent section)
   - Ensure wires are secured and won't interfere with camera

### 2. Enable Power Saving in Configuration

**Edit configuration file:**
```bash
nano /home/fishcam/Desktop/FishCam/FishCam/scripts/fishcam_config.yaml
```

**Set power saving to enabled:**
```yaml
power_saving:
  enabled: true  # Set to true to enable power saving mode
  reed_switch_pin: 18  # GPIO pin for reed switch (default: 18)
  led_pin: 23  # GPIO pin for LED (default: 23)
  check_interval: 2.0  # Check interval in seconds

  # Audio feedback when in configuration mode
  beep_in_config_mode: false  # Set to true to enable periodic beeps when magnet is near
  beep_interval: 10.0  # Interval between beeps in seconds
  beep_duration: 0.1  # Duration of each beep in seconds
```

**To disable power saving** (for FishCams without reed switch hardware):
```yaml
power_saving:
  enabled: false  # Set to false to disable power saving mode
```

When disabled, the power saving script will exit gracefully and the FishCam operates normally.

### 3. Software Installation

1. **Script is already included:**
   ```bash
   # Script location:
   /home/fishcam/Desktop/FishCam/FishCam/scripts/powerSavingMode.py
   ```

2. **Make script executable:**
   ```bash
   chmod +x /home/fishcam/Desktop/FishCam/FishCam/scripts/powerSavingMode.py
   ```

3. **Test script manually (only if enabled in config):**
   ```bash
   # Run in foreground to test
   sudo python3 /home/fishcam/Desktop/FishCam/FishCam/scripts/powerSavingMode.py
   ```

   **If enabled:**
   - Test with magnet near reed switch (LED should turn ON)
   - Remove magnet (LED should turn OFF)
   - Check log: `/home/fishcam/Desktop/FishCam/logs/power_saving.log`

   **If disabled:**
   - Script will log "Power saving mode is DISABLED" and exit gracefully

### 4. Configure Auto-Start

**Edit camStartup.sh:**

```bash
nano /home/fishcam/Desktop/FishCam/FishCam/scripts/camStartup.sh
```

**Add this line at the beginning (after the shebang):**

```bash
#!/bin/bash

# Start power saving mode controller in background
sudo python3 /home/fishcam/Desktop/FishCam/FishCam/scripts/powerSavingMode.py >> /home/fishcam/Desktop/FishCam/logs/power_saving_startup.log 2>&1 &

# Wait a moment for power saving to initialize
sleep 3

# ... rest of camStartup.sh
```

**The controller will now:**
- Start automatically on boot (via cron job)
- Run in background (if enabled in config)
- Monitor reed switch every 2 seconds (if enabled)
- Log all mode changes to `logs/power_saving.log`
- Exit gracefully if disabled in configuration

### 5. Reboot and Test

```bash
sudo reboot
```

After reboot:
1. LED should be OFF (power saving mode)
2. WiFi should be disabled
3. Bring magnet near reed switch
4. LED should turn ON within 2 seconds
5. WiFi should become available

---

## Usage

### During Configuration/Testing

1. **Bring magnet near reed switch**
2. **Wait 2 seconds** for mode to switch
3. **LED turns ON** - Configuration mode active
4. **Optional: Buzzer beeps every 10 seconds** (if enabled) - Audio confirmation of config mode
5. **WiFi is enabled** - can SSH or connect
6. **HDMI is active** - can connect display

**Tip:** Enable `beep_in_config_mode: true` if you want audio feedback that the system is in configuration mode. This is useful when the LED is not visible or not installed.

### During Deployment

1. **Remove magnet from reed switch**
2. **Wait 2 seconds** for mode to switch
3. **LED turns OFF** - Power saving mode active
4. **Beeping stops** (if it was enabled)
5. **WiFi disabled** - no wireless power draw
6. **CPU throttled** - reduced power consumption

---

## Power Savings Estimate

**Power Saving Mode Reductions:**
- WiFi disabled: ~40-50mA savings
- Bluetooth disabled: ~10-15mA savings
- HDMI disabled: ~20-30mA savings
- CPU throttled (600 MHz vs 1000 MHz): ~50-100mA savings
- Services stopped: ~10-20mA savings

**Total estimated savings: 130-215mA**

For a typical deployment:
- Video recording: ~250-300mA (camera + encoding)
- Power saving mode: ~130-215mA reduction
- **Net power consumption: ~135-170mA** (vs ~300mA without power saving)

This can **extend battery life by 40-50%** depending on battery capacity and deployment duration.

---

## Troubleshooting

### LED doesn't turn on

1. Check LED polarity (anode to resistor, cathode to GND)
2. Check resistor value (should be 220-330Ω)
3. Test with multimeter: GPIO 27 should show 3.3V when high
4. Check logs: `cat /home/fishcam/Desktop/FishCam/logs/power_saving.log`

### Reed switch doesn't work

1. Test reed switch with multimeter (should close with magnet near)
2. Check GPIO 17 connection
3. Verify magnet is strong enough (bring very close to switch)
4. Check logs for GPIO initialization errors

### Mode doesn't change

1. Check if script is running: `ps aux | grep powerSavingMode`
2. Check logs: `tail -f /home/fishcam/Desktop/FishCam/logs/power_saving.log`
3. Verify sudo permissions
4. Test script manually first

### WiFi doesn't come back

1. Manually unblock: `sudo rfkill unblock wifi`
2. Restart networking: `sudo systemctl restart networking`
3. Check rfkill status: `sudo rfkill list`

---

## Advanced Configuration

### Change GPIO Pins

Edit `fishcam_config.yaml`:

```yaml
power_saving:
  enabled: true
  reed_switch_pin: 18  # Change to your pin number (BCM numbering)
  led_pin: 23          # Change to your pin number (BCM numbering)
  check_interval: 2.0
```

**Common GPIO pins on right side:**
- GPIO 18 (Pin 12), GPIO 23 (Pin 16), GPIO 24 (Pin 18), GPIO 25 (Pin 22)

### Change Check Interval

Edit `fishcam_config.yaml`:

```yaml
power_saving:
  enabled: true
  reed_switch_pin: 18
  led_pin: 23
  check_interval: 5.0  # Increase to save more power (slower response)
```

**Recommendation:** 2-5 seconds provides good balance between responsiveness and power consumption.

### Customize Power Saving Actions

Edit the `enter_power_saving_mode()` function to enable/disable specific power saving features.

**Example - Enable USB Autosuspend (aggressive power saving):**

**In `enter_power_saving_mode()` function**, uncomment:
```python
# Disable USB (can save significant power, but be careful with camera)
logging.info("Disabling USB...")
self.run_command("echo auto | sudo tee /sys/bus/usb/devices/usb1/power/control")
```

**In `enter_config_mode()` function**, uncomment:
```python
# Re-enable USB (disable autosuspend for normal operation)
logging.info("Enabling USB...")
self.run_command("echo on | sudo tee /sys/bus/usb/devices/usb1/power/control")
```

**Warning:** Only enable USB autosuspend if camera doesn't use USB interface (check your specific camera module). Both disable and enable must be uncommented together to ensure USB works properly in config mode.

---

## Safety Notes

1. **Test thoroughly before deployment** - Ensure video recording works in power saving mode
2. **Keep magnet accessible** - You need it to configure the system
3. **Check logs after deployment** - Verify power saving activated correctly
4. **Battery capacity** - Ensure battery can handle full deployment duration even without power saving
5. **SD card** - Power saving doesn't reduce SD card writes; ensure sufficient capacity
