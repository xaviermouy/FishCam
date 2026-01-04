#!/bin/bash
# FishCam Power Saving Status Check
# Provides comprehensive report on all power saving components

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Symbols
CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"

echo "================================================================="
echo "          FishCam Power Saving Status Report"
echo "================================================================="
echo ""

# Get current timestamp
echo -e "${BLUE}Report Time:${NC} $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ================================================================
# Power Saving Mode Detection
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}POWER SAVING MODE${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check if powerSavingMode.py is running
if pgrep -f "powerSavingMode.py" > /dev/null; then
    echo -e "Power Saving Script: ${CHECK} Running"

    # Try to determine mode from recent logs
    if [ -f /home/fishcam/Desktop/FishCam/logs/power_saving.log ]; then
        LAST_MODE=$(tail -50 /home/fishcam/Desktop/FishCam/logs/power_saving.log | grep -E "(power saving mode activated|Configuration mode activated)" | tail -1)
        if echo "$LAST_MODE" | grep -q "power saving"; then
            echo -e "Current Mode:        ${GREEN}Power Saving Mode${NC}"
            EXPECTED_MODE="power_saving"
        elif echo "$LAST_MODE" | grep -q "Configuration"; then
            echo -e "Current Mode:        ${YELLOW}Configuration Mode${NC}"
            EXPECTED_MODE="config"
        else
            echo -e "Current Mode:        ${WARN} Unknown (check logs)"
            EXPECTED_MODE="unknown"
        fi
    fi
else
    echo -e "Power Saving Script: ${CROSS} Not Running"
    EXPECTED_MODE="unknown"
fi
echo ""

# ================================================================
# CPU Frequency
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}CPU FREQUENCY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    GOVERNOR=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
    MIN_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq)
    MAX_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq)
    CUR_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)

    echo -e "Governor:            ${GOVERNOR}"
    echo -e "Min Frequency:       $((MIN_FREQ/1000)) MHz"
    echo -e "Max Frequency:       $((MAX_FREQ/1000)) MHz"
    echo -e "Current Frequency:   $((CUR_FREQ/1000)) MHz"

    # Check if settings match expected mode
    if [ "$EXPECTED_MODE" = "power_saving" ]; then
        if [ "$GOVERNOR" = "powersave" ] && [ "$MAX_FREQ" -le 600000 ]; then
            echo -e "Status:              ${CHECK} Correctly throttled"
        else
            echo -e "Status:              ${WARN} Expected powersave governor & 600 MHz cap"
        fi
    elif [ "$EXPECTED_MODE" = "config" ]; then
        if [ "$GOVERNOR" = "ondemand" ] && [ "$MAX_FREQ" -ge 1000000 ]; then
            echo -e "Status:              ${CHECK} Full performance available"
        else
            echo -e "Status:              ${WARN} Expected ondemand governor & 1000 MHz cap"
        fi
    fi

    # Show per-core frequencies if available
    echo ""
    echo "Per-Core Frequencies:"
    for cpu in 0 1 2 3; do
        if [ -f /sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_cur_freq ]; then
            FREQ=$(cat /sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_cur_freq)
            echo -e "  CPU${cpu}: $((FREQ/1000)) MHz"
        fi
    done
else
    echo -e "${CROSS} CPU frequency scaling not available"
fi

# CPU Temperature
if command -v vcgencmd &> /dev/null; then
    TEMP=$(vcgencmd measure_temp | cut -d= -f2)
    echo -e "\nTemperature:         ${TEMP}"
fi
echo ""

# ================================================================
# WiFi Status
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}WiFi${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check WiFi radio status
WIFI_RADIO=$(nmcli radio wifi)
if [ "$WIFI_RADIO" = "enabled" ]; then
    echo -e "Radio Status:        ${CHECK} Enabled"

    # Check connection
    WIFI_CONN=$(nmcli -t -f GENERAL.CONNECTION dev show wlan0 2>/dev/null | cut -d: -f2)
    if [ -n "$WIFI_CONN" ] && [ "$WIFI_CONN" != "--" ]; then
        echo -e "Connected:           ${CHECK} Yes"
        echo -e "Network:             ${WIFI_CONN}"

        # Get IP address
        IP_ADDR=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        if [ -n "$IP_ADDR" ]; then
            echo -e "IP Address:          ${IP_ADDR}"
        fi

        # Signal strength
        SIGNAL=$(nmcli -t -f GENERAL.SIGNAL dev show wlan0 2>/dev/null | cut -d: -f2)
        if [ -n "$SIGNAL" ]; then
            echo -e "Signal Strength:     ${SIGNAL}%"
        fi
    else
        echo -e "Connected:           ${CROSS} No"
    fi

    # Check against expected mode
    if [ "$EXPECTED_MODE" = "power_saving" ]; then
        echo -e "Status:              ${WARN} Should be disabled in power saving mode"
    elif [ "$EXPECTED_MODE" = "config" ]; then
        echo -e "Status:              ${CHECK} Correctly enabled"
    fi
else
    echo -e "Radio Status:        ${CROSS} Disabled"
    echo -e "Connected:           No"

    if [ "$EXPECTED_MODE" = "power_saving" ]; then
        echo -e "Status:              ${CHECK} Correctly disabled"
    elif [ "$EXPECTED_MODE" = "config" ]; then
        echo -e "Status:              ${WARN} Should be enabled in config mode"
    fi
fi
echo ""

# ================================================================
# Bluetooth Status
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}BLUETOOTH${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check rfkill status for bluetooth
BT_BLOCKED=$(rfkill list bluetooth 2>/dev/null | grep -c "Soft blocked: yes")
BT_EXISTS=$(rfkill list bluetooth 2>/dev/null | grep -c "bluetooth")

if [ "$BT_EXISTS" -gt 0 ]; then
    if [ "$BT_BLOCKED" -gt 0 ]; then
        echo -e "Status:              ${CROSS} Blocked/Disabled"
        if [ "$EXPECTED_MODE" = "power_saving" ]; then
            echo -e "Expected:            ${CHECK} Correctly disabled"
        fi
    else
        echo -e "Status:              ${CHECK} Enabled"
        if [ "$EXPECTED_MODE" = "config" ]; then
            echo -e "Expected:            ${CHECK} Correctly enabled"
        fi
    fi

    # Check bluetooth service
    if systemctl is-active --quiet bluetooth; then
        echo -e "Service:             ${CHECK} Running"
    else
        echo -e "Service:             ${CROSS} Stopped"
    fi
else
    echo -e "${WARN} Bluetooth hardware not found"
fi
echo ""

# ================================================================
# HDMI Status
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}HDMI${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if command -v tvservice &> /dev/null; then
    HDMI_STATUS=$(tvservice -s 2>&1)
    if echo "$HDMI_STATUS" | grep -q "0x120002"; then
        echo -e "Status:              ${CROSS} Off (blanked)"
        if [ "$EXPECTED_MODE" = "power_saving" ]; then
            echo -e "Expected:            ${CHECK} Correctly disabled"
        fi
    elif echo "$HDMI_STATUS" | grep -q "0x12000a"; then
        echo -e "Status:              ${CHECK} On"
        if [ "$EXPECTED_MODE" = "config" ]; then
            echo -e "Expected:            ${CHECK} Correctly enabled"
        fi
    else
        echo -e "Status:              ${WARN} Unknown state"
        echo -e "Details:             ${HDMI_STATUS}"
    fi
else
    echo -e "${WARN} tvservice command not available"
fi
echo ""

# ================================================================
# USB Power Status
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}USB${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -f /sys/bus/usb/devices/usb1/power/control ]; then
    USB_CONTROL=$(cat /sys/bus/usb/devices/usb1/power/control)
    echo -e "Power Control:       ${USB_CONTROL}"

    if [ "$USB_CONTROL" = "auto" ]; then
        echo -e "Status:              ${YELLOW} Autosuspend enabled (power saving)${NC}"
        if [ "$EXPECTED_MODE" = "power_saving" ]; then
            echo -e "Expected:            ${CHECK} Correctly in autosuspend"
        fi
    elif [ "$USB_CONTROL" = "on" ]; then
        echo -e "Status:              ${GREEN} Always on (full power)${NC}"
        if [ "$EXPECTED_MODE" = "config" ]; then
            echo -e "Expected:            ${CHECK} Correctly enabled"
        fi
    fi
else
    echo -e "${WARN} USB power control not available"
fi
echo ""

# ================================================================
# Services Status
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SERVICES${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check key services
for service in avahi-daemon bluetooth triggerhappy; do
    if systemctl list-unit-files | grep -q "^${service}.service"; then
        if systemctl is-active --quiet ${service}; then
            echo -e "${service}:$(printf '%*s' $((20-${#service})) '')${CHECK} Running"
        else
            echo -e "${service}:$(printf '%*s' $((20-${#service})) '')${CROSS} Stopped"
        fi
    else
        echo -e "${service}:$(printf '%*s' $((20-${#service})) '')${WARN} Not installed"
    fi
done
echo ""

# ================================================================
# LED Triggers
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}LED TRIGGERS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Activity LED (led0)
if [ -f /sys/class/leds/led0/trigger ]; then
    LED0_TRIGGER=$(cat /sys/class/leds/led0/trigger | grep -o '\[.*\]' | tr -d '[]')
    echo -e "Activity LED (led0): ${LED0_TRIGGER}"
    if [ "$LED0_TRIGGER" = "none" ]; then
        echo -e "                     ${YELLOW}Disabled (power saving)${NC}"
    else
        echo -e "                     ${GREEN}Active${NC}"
    fi
fi

# Power LED (led1) if controllable
if [ -f /sys/class/leds/led1/trigger ]; then
    LED1_TRIGGER=$(cat /sys/class/leds/led1/trigger | grep -o '\[.*\]' | tr -d '[]')
    echo -e "Power LED (led1):    ${LED1_TRIGGER}"
fi
echo ""

# ================================================================
# GPIO Status (Reed Switch & Status LED)
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}GPIO PINS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Try to read GPIO states (requires root for some access)
if [ -r /sys/kernel/debug/gpio ]; then
    echo "GPIO Usage:"
    grep -E "gpio-18|gpio-23" /sys/kernel/debug/gpio 2>/dev/null || echo "  (Requires root for detailed GPIO info)"
else
    echo "Reed Switch (GPIO18): Configured in powerSavingMode.py"
    echo "Status LED (GPIO23):  Configured in powerSavingMode.py"
fi
echo ""

# ================================================================
# Power Consumption Estimate
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}ESTIMATED POWER SAVINGS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

SAVINGS=0

# WiFi
if [ "$WIFI_RADIO" = "disabled" ]; then
    echo -e "WiFi disabled:       ${GREEN}~45 mA saved${NC}"
    SAVINGS=$((SAVINGS + 45))
fi

# Bluetooth
if [ "$BT_BLOCKED" -gt 0 ]; then
    echo -e "Bluetooth disabled:  ${GREEN}~12 mA saved${NC}"
    SAVINGS=$((SAVINGS + 12))
fi

# CPU throttling
if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq ]; then
    MAX_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq)
    if [ "$MAX_FREQ" -le 600000 ]; then
        echo -e "CPU throttled:       ${GREEN}~75 mA saved${NC}"
        SAVINGS=$((SAVINGS + 75))
    fi
fi

# HDMI
if echo "$HDMI_STATUS" | grep -q "0x120002"; then
    echo -e "HDMI disabled:       ${GREEN}~25 mA saved${NC}"
    SAVINGS=$((SAVINGS + 25))
fi

echo ""
echo -e "Total Estimated:     ${GREEN}~${SAVINGS} mA saved${NC}"
echo ""

# ================================================================
# Summary
# ================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "$EXPECTED_MODE" = "power_saving" ]; then
    echo -e "Expected Mode:       ${GREEN}Power Saving${NC}"
    echo -e "Power savings active for battery-powered deployment"
elif [ "$EXPECTED_MODE" = "config" ]; then
    echo -e "Expected Mode:       ${YELLOW}Configuration${NC}"
    echo -e "Full power available for setup and access"
else
    echo -e "Expected Mode:       ${WARN} Unknown"
    echo -e "Power saving script may not be running"
fi

echo ""
echo "================================================================="
echo "End of Report"
echo "================================================================="
