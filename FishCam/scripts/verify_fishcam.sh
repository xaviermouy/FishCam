#!/bin/bash
# verify_fishcam.sh
# Run this manually on a fishcam via SSH to check and fix its setup.
# Verifies pip packages, cron job, repo state, permissions, and system config.
# Auto-fixes what it safely can; reports items that require manual action.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
WITTYPI_DIR="/home/fishcam/Desktop/wittypi"
STARTUP_SCRIPT="$SCRIPT_DIR/fishcamStartup.sh"
CONFIG_TXT="/boot/firmware/config.txt"
JOURNAL_DIR="/var/log/journal"

FISHCAM_USER="${SUDO_USER:-${USER}}"

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

pass()   { echo -e "  ${GREEN}[OK]${RESET}     $1"; }
fail()   { echo -e "  ${RED}[FAIL]${RESET}   $1"; FAILURES=$((FAILURES + 1)); }
fixed()  { echo -e "  ${CYAN}[FIXED]${RESET}  $1"; FIXES=$((FIXES + 1)); }
warn()   { echo -e "  ${YELLOW}[WARN]${RESET}   $1"; WARNINGS=$((WARNINGS + 1)); }
info()   { echo -e "           $1"; }

FAILURES=0
FIXES=0
WARNINGS=0

# ── Helpers ───────────────────────────────────────────────────────────────────

pip_installed() {
    python3 -c "import importlib.util; exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null
}

pip_package_name() {
    # Map import name → pip package name where they differ
    case "$1" in
        adafruit_blinka) echo "adafruit-blinka" ;;
        adafruit_bno08x) echo "adafruit-circuitpython-bno08x" ;;
        *)               echo "$1" ;;
    esac
}

pip_install_pkg() {
    local import_name="$1"
    local pip_name
    pip_name="$(pip_package_name "$import_name")"
    if pip install --break-system-packages "$pip_name" -q 2>/dev/null \
       || pip install "$pip_name" -q 2>/dev/null; then
        fixed "Installed missing package: $pip_name"
    else
        fail "Could not install $pip_name — install manually: pip install $pip_name"
    fi
}

# ── Header ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  FishCam Verify & Fix — $(hostname)${RESET}"
echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
echo ""

# ── 1. Hostname ───────────────────────────────────────────────────────────────

echo -e "${BOLD}  IDENTITY${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

hostname_val="$(hostname)"
if echo "$hostname_val" | grep -qE '^fishcam[0-9]+$'; then
    pass "Hostname: $hostname_val"
else
    warn "Hostname '$hostname_val' does not match 'fishcamXX' pattern"
    info "Change via: sudo raspi-config > System > Hostname"
fi
echo ""

# ── 2. Python packages ────────────────────────────────────────────────────────

echo -e "${BOLD}  PYTHON PACKAGES${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

declare -A PACKAGES=(
    ["yaml"]="pyyaml"
    ["flask"]="flask"
    ["adafruit_blinka"]="adafruit-blinka"
    ["adafruit_bno08x"]="adafruit-circuitpython-bno08x"
)

for import_name in yaml flask adafruit_blinka adafruit_bno08x; do
    pip_name="${PACKAGES[$import_name]}"
    if pip_installed "$import_name"; then
        pass "$pip_name"
    else
        pip_install_pkg "$import_name"
    fi
done
echo ""

# ── 3. Cron job ───────────────────────────────────────────────────────────────

echo -e "${BOLD}  CRON JOB${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

CRON_ENTRY="@reboot sh $STARTUP_SCRIPT &"

if crontab -l 2>/dev/null | grep -qF "fishcamStartup.sh"; then
    pass "Startup cron job present"
    # Show the actual line for verification
    actual_line="$(crontab -l 2>/dev/null | grep "fishcamStartup.sh")"
    info "→ $actual_line"
else
    # Add the cron entry
    ( crontab -l 2>/dev/null; echo "$CRON_ENTRY" ) | crontab -
    if crontab -l 2>/dev/null | grep -qF "fishcamStartup.sh"; then
        fixed "Added missing cron job: $CRON_ENTRY"
    else
        fail "Could not add cron job — add manually: crontab -e"
        info "Entry to add: $CRON_ENTRY"
    fi
fi
echo ""

# ── 4. GitHub repository ──────────────────────────────────────────────────────

echo -e "${BOLD}  GITHUB REPOSITORY${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

if [ ! -d "$REPO_DIR/.git" ]; then
    fail "Repository not found at $REPO_DIR"
else
    # Fetch quietly to get current remote state
    if git -C "$REPO_DIR" fetch origin --quiet 2>/dev/null; then
        local_hash="$(git -C "$REPO_DIR" rev-parse HEAD)"
        remote_hash="$(git -C "$REPO_DIR" rev-parse origin/main 2>/dev/null || echo '')"

        if [ "$local_hash" = "$remote_hash" ]; then
            pass "Repository up to date ($(git -C "$REPO_DIR" rev-parse --short HEAD))"
        else
            behind="$(git -C "$REPO_DIR" rev-list --count HEAD..origin/main)"
            info "Repository is $behind commit(s) behind origin/main — updating..."
            if bash "$SCRIPT_DIR/updateFishCamRepo.sh"; then
                fixed "Repository updated to $(git -C "$REPO_DIR" rev-parse --short HEAD)"
            else
                fail "Repository update failed — run updateFishCamRepo.sh manually"
            fi
        fi
    else
        warn "Could not reach GitHub (no internet?) — skipping repo update"
        info "Current commit: $(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
    fi
fi
echo ""

# ── 5. WittyPi ────────────────────────────────────────────────────────────────

echo -e "${BOLD}  WITTYPI${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

if [ ! -d "$WITTYPI_DIR" ]; then
    fail "WittyPi not found at $WITTYPI_DIR — install from: http://www.uugear.com/repo/WittyPi4/install.sh"
else
    pass "WittyPi directory exists"

    # Check ownership
    dir_owner="$(stat -c '%U' "$WITTYPI_DIR")"
    if [ "$dir_owner" = "root" ]; then
        sudo chown -R "$FISHCAM_USER:$FISHCAM_USER" "$WITTYPI_DIR" 2>/dev/null \
            && fixed "Fixed WittyPi directory ownership ($dir_owner → $FISHCAM_USER)" \
            || fail "Could not fix WittyPi ownership — run: sudo chown -R $FISHCAM_USER:$FISHCAM_USER $WITTYPI_DIR"
    else
        pass "WittyPi directory owned by $dir_owner"
    fi

    # Check wittyPi.log ownership
    WITTYPI_LOG="$WITTYPI_DIR/wittyPi.log"
    if [ -f "$WITTYPI_LOG" ]; then
        log_owner="$(stat -c '%U' "$WITTYPI_LOG")"
        if [ "$log_owner" = "root" ]; then
            sudo chown "$FISHCAM_USER:$FISHCAM_USER" "$WITTYPI_LOG" 2>/dev/null \
                && fixed "Fixed wittyPi.log ownership (root → $FISHCAM_USER)" \
                || fail "Could not fix wittyPi.log ownership — run: sudo chown $FISHCAM_USER:$FISHCAM_USER $WITTYPI_LOG"
        else
            pass "wittyPi.log owned by $log_owner"
        fi
    else
        pass "wittyPi.log not yet created (will be created on first run)"
    fi
fi
echo ""

# ── 6. User groups ────────────────────────────────────────────────────────────

echo -e "${BOLD}  USER GROUPS${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

if groups "$FISHCAM_USER" 2>/dev/null | grep -qw "i2c"; then
    pass "$FISHCAM_USER is in the i2c group"
else
    sudo usermod -aG i2c "$FISHCAM_USER" 2>/dev/null \
        && fixed "Added $FISHCAM_USER to i2c group (log out and back in, or reboot)" \
        || fail "Could not add $FISHCAM_USER to i2c group — run: sudo usermod -aG i2c $FISHCAM_USER"
fi
echo ""

# ── 7. System journal ─────────────────────────────────────────────────────────

echo -e "${BOLD}  SYSTEM JOURNAL${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

if [ -d "$JOURNAL_DIR" ] && ls "$JOURNAL_DIR"/*/system.journal &>/dev/null; then
    pass "Persistent journal enabled ($JOURNAL_DIR)"
else
    warn "Journal does not appear to be persistent"
    info "Enable via: sudo raspi-config > Advanced Options > Logging > Persistent"
fi
echo ""

# ── 8. Hardware config (report only) ─────────────────────────────────────────

echo -e "${BOLD}  HARDWARE CONFIGURATION  (report only — manual changes required)${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

# I2C enabled
if grep -qE '^dtparam=i2c_arm=on' "$CONFIG_TXT" 2>/dev/null; then
    pass "I2C enabled in $CONFIG_TXT"
else
    warn "I2C may not be enabled — check: sudo raspi-config > Interfaces > I2C"
fi

# I2C baud rate
if grep -qE 'i2c_arm_baudrate=100000' "$CONFIG_TXT" 2>/dev/null; then
    pass "I2C baud rate set to 100 kHz"
else
    warn "I2C baud rate not set to 100 kHz (IMU stability)"
    info "In $CONFIG_TXT, change dtparam=i2c_arm=on"
    info "     to:  dtparam=i2c_arm=on,i2c_arm_baudrate=100000"
fi

# SSH enabled
if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
    pass "SSH is active"
else
    warn "SSH does not appear to be running — check: sudo raspi-config > Interfaces > SSH"
fi

# Filesystem expanded — compare partition size to SD card size
ROOT_SIZE_KB="$(df / --output=size | tail -1 | tr -d ' ')"
ROOT_SIZE_GB=$(( ROOT_SIZE_KB / 1024 / 1024 ))
if [ "$ROOT_SIZE_GB" -ge 8 ]; then
    pass "Filesystem appears expanded (${ROOT_SIZE_GB} GB visible)"
else
    warn "Filesystem may not be fully expanded (only ${ROOT_SIZE_GB} GB visible)"
    info "Expand via: sudo raspi-config > Advanced Options > Expand Filesystem"
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  SUMMARY${RESET}"
echo "  ──────────────────────────────────────────────────────────────"

if [ "$FIXES" -gt 0 ]; then
    echo -e "  ${CYAN}${FIXES} item(s) auto-fixed${RESET}"
fi
if [ "$WARNINGS" -gt 0 ]; then
    echo -e "  ${YELLOW}${WARNINGS} warning(s) require manual attention${RESET}"
fi
if [ "$FAILURES" -gt 0 ]; then
    echo -e "  ${RED}${FAILURES} item(s) failed — see details above${RESET}"
fi
if [ "$FAILURES" -eq 0 ] && [ "$WARNINGS" -eq 0 ] && [ "$FIXES" -eq 0 ]; then
    echo -e "  ${GREEN}All checks passed — nothing to do.${RESET}"
fi

echo -e "${BOLD}════════════════════════════════════════════════════════════════${RESET}"
echo ""

# Exit with non-zero if anything failed (useful if called from a wrapper later)
[ "$FAILURES" -eq 0 ]
