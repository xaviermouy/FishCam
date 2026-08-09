#!/bin/bash
# verify_fishcam.sh
# Run this manually on a fishcam via SSH to check and fix its setup.
# Verifies pip packages, cron job, repo state, permissions, and system config.
# Auto-fixes what it safely can; reports items that require manual action.

# Guard: re-exec with bash if invoked via sh (dash doesn't support all features used here)
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

pass()   { printf "  ${GREEN}[OK]${RESET}     %s\n" "$1"; }
fail()   { printf "  ${RED}[FAIL]${RESET}   %s\n" "$1"; FAILURES=$((FAILURES + 1)); }
fixed()  { printf "  ${CYAN}[FIXED]${RESET}  %s\n" "$1"; FIXES=$((FIXES + 1)); }
warn()   { printf "  ${YELLOW}[WARN]${RESET}   %s\n" "$1"; WARNINGS=$((WARNINGS + 1)); }
info()   { printf "           %s\n" "$1"; }

FAILURES=0
FIXES=0
WARNINGS=0

# ── Helpers ───────────────────────────────────────────────────────────────────

pip_installed() {
    python3 -c "import importlib.util; exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null
}

pip_install_pkg() {
    local import_name="$1"
    local pip_name="$2"
    if pip install --break-system-packages "$pip_name" -q 2>/dev/null \
       || pip install "$pip_name" -q 2>/dev/null; then
        fixed "Installed missing package: $pip_name"
    else
        fail "Could not install $pip_name — install manually: pip install $pip_name"
    fi
}

# ── Header ────────────────────────────────────────────────────────────────────

printf "\n"
printf "${BOLD}════════════════════════════════════════════════════════════════${RESET}\n"
printf "${BOLD}  FishCam Verify & Fix — %s${RESET}\n" "$(hostname)"
printf "${BOLD}════════════════════════════════════════════════════════════════${RESET}\n"
printf "\n"

# ── 1. Hostname ───────────────────────────────────────────────────────────────

printf "${BOLD}  IDENTITY${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

hostname_val="$(hostname)"
if echo "$hostname_val" | grep -qE '^fishcam[0-9]+$'; then
    pass "Hostname: $hostname_val"
else
    warn "Hostname '$hostname_val' does not match 'fishcamXX' pattern"
    info "Fix: sudo raspi-config"
    info "     > System Options > Hostname"
    info "     Set to fishcam01, fishcam02, etc. then reboot."
fi
printf "\n"

# ── 2. Python packages ────────────────────────────────────────────────────────

printf "${BOLD}  PYTHON PACKAGES${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

# Format: "import_name:pip_package_name"
PACKAGE_LIST="yaml:pyyaml flask:flask adafruit_blinka:adafruit-blinka adafruit_bno08x:adafruit-circuitpython-bno08x"

for entry in $PACKAGE_LIST; do
    import_name="${entry%%:*}"
    pip_name="${entry##*:}"
    if pip_installed "$import_name"; then
        pass "$pip_name"
    else
        pip_install_pkg "$import_name" "$pip_name"
    fi
done
printf "\n"

# ── 3. Cron job ───────────────────────────────────────────────────────────────

printf "${BOLD}  CRON JOB${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

CRON_ENTRY="@reboot sh $STARTUP_SCRIPT &"

if crontab -l 2>/dev/null | grep -qF "fishcamStartup.sh"; then
    pass "Startup cron job present"
    actual_line="$(crontab -l 2>/dev/null | grep "fishcamStartup.sh")"
    info "→ $actual_line"
else
    ( crontab -l 2>/dev/null; echo "$CRON_ENTRY" ) | crontab -
    if crontab -l 2>/dev/null | grep -qF "fishcamStartup.sh"; then
        fixed "Added missing cron job: $CRON_ENTRY"
    else
        fail "Could not add cron job — add manually: crontab -e"
        info "Entry to add: $CRON_ENTRY"
    fi
fi
printf "\n"

# ── 4. GitHub repository ──────────────────────────────────────────────────────

printf "${BOLD}  GITHUB REPOSITORY${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if [ ! -d "$REPO_DIR/.git" ]; then
    fail "Repository not found at $REPO_DIR"
else
    if git -C "$REPO_DIR" fetch origin --quiet 2>/dev/null; then
        local_hash="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo '')"
        remote_hash="$(git -C "$REPO_DIR" rev-parse origin/main 2>/dev/null || echo '')"

        if [ -z "$remote_hash" ]; then
            warn "Could not resolve origin/main — remote tracking branch missing"
            info "Fix: cd $REPO_DIR"
            info "     git remote set-url origin https://github.com/xaviermouy/FishCam.git"
            info "     git fetch origin"
            info "     git checkout -B main origin/main"
            info "Current commit: $(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
        elif [ "$local_hash" = "$remote_hash" ]; then
            pass "Repository up to date ($(git -C "$REPO_DIR" rev-parse --short HEAD))"
        else
            behind="$(git -C "$REPO_DIR" rev-list --count HEAD..origin/main 2>/dev/null || echo '?')"
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
printf "\n"

# ── 5. WittyPi ────────────────────────────────────────────────────────────────

printf "${BOLD}  WITTYPI${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if [ ! -d "$WITTYPI_DIR" ]; then
    fail "WittyPi not found at $WITTYPI_DIR"
    info "Fix: cd /home/fishcam/Desktop"
    info "     wget http://www.uugear.com/repo/WittyPi4/install.sh"
    info "     sudo sh install.sh"
    info "     sudo chown -R fishcam:fishcam $WITTYPI_DIR"
else
    pass "WittyPi directory exists"

    dir_owner="$(stat -c '%U' "$WITTYPI_DIR")"
    if [ "$dir_owner" = "root" ]; then
        sudo chown -R "$FISHCAM_USER:$FISHCAM_USER" "$WITTYPI_DIR" 2>/dev/null \
            && fixed "Fixed WittyPi directory ownership ($dir_owner → $FISHCAM_USER)" \
            || fail "Could not fix WittyPi ownership — run: sudo chown -R $FISHCAM_USER:$FISHCAM_USER $WITTYPI_DIR"
    else
        pass "WittyPi directory owned by $dir_owner"
    fi

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
printf "\n"

# ── 6. User groups ────────────────────────────────────────────────────────────

printf "${BOLD}  USER GROUPS${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if groups "$FISHCAM_USER" 2>/dev/null | grep -qw "i2c"; then
    pass "$FISHCAM_USER is in the i2c group"
else
    sudo usermod -aG i2c "$FISHCAM_USER" 2>/dev/null \
        && fixed "Added $FISHCAM_USER to i2c group (log out and back in, or reboot)" \
        || fail "Could not add $FISHCAM_USER to i2c group — run: sudo usermod -aG i2c $FISHCAM_USER"
fi
printf "\n"

# ── 7. System journal ─────────────────────────────────────────────────────────

printf "${BOLD}  SYSTEM JOURNAL${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if [ -d "$JOURNAL_DIR" ] && ls "$JOURNAL_DIR"/*/system.journal &>/dev/null; then
    pass "Persistent journal enabled ($JOURNAL_DIR)"
else
    warn "Journal does not appear to be persistent (boot logs lost on reboot)"
    info "Fix: sudo raspi-config"
    info "     > Advanced Options > Logging > Persistent"
    info "     Reboot when prompted, then verify with: ls /var/log/journal/"
    info "     NOTE: use raspi-config only — the manual mkdir method does not"
    info "     work on Pi Zero W (no systemd-journald-flush.service)."
fi
printf "\n"

# ── 8. Hardware config (report only) ─────────────────────────────────────────

printf "${BOLD}  HARDWARE CONFIGURATION  (report only — manual changes required)${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if grep -qE '^dtparam=i2c_arm=on' "$CONFIG_TXT" 2>/dev/null; then
    pass "I2C enabled in $CONFIG_TXT"
else
    warn "I2C not enabled (IMU and WittyPi will not work)"
    info "Fix: sudo raspi-config"
    info "     > Interface Options > I2C > Yes"
    info "     Reboot when prompted, then verify with: sudo i2cdetect -y 1"
fi

if grep -qE 'i2c_arm_baudrate=100000' "$CONFIG_TXT" 2>/dev/null; then
    pass "I2C baud rate set to 100 kHz"
else
    warn "I2C baud rate not set to 100 kHz (may cause IMU communication errors)"
    info "Fix: sudo nano $CONFIG_TXT"
    info "     Find:    dtparam=i2c_arm=on"
    info "     Replace: dtparam=i2c_arm=on,i2c_arm_baudrate=100000"
    info "     Save (Ctrl+O, Enter, Ctrl+X), then reboot."
    info "     Verify:  grep baudrate $CONFIG_TXT"
    info "     (should show 000186a0 = 100000 in hex)"
fi

if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
    pass "SSH is active"
else
    warn "SSH is not running (you will lose remote access after reboot)"
    info "Fix: sudo raspi-config"
    info "     > Interface Options > SSH > Yes"
    info "     No reboot needed — SSH starts immediately."
fi

ROOT_SIZE_KB="$(df / --output=size | tail -1 | tr -d ' ')"
ROOT_SIZE_GB=$(( ROOT_SIZE_KB / 1024 / 1024 ))
if [ "$ROOT_SIZE_GB" -ge 8 ]; then
    pass "Filesystem appears expanded (${ROOT_SIZE_GB} GB visible)"
else
    warn "Filesystem not fully expanded — only ${ROOT_SIZE_GB} GB visible (wasted SD space)"
    info "Fix: sudo raspi-config"
    info "     > Advanced Options > Expand Filesystem"
    info "     Reboot when prompted, then verify with: df -h /"
fi

printf "\n"

# ── Summary ───────────────────────────────────────────────────────────────────

printf "${BOLD}════════════════════════════════════════════════════════════════${RESET}\n"
printf "${BOLD}  SUMMARY${RESET}\n"
printf "  ──────────────────────────────────────────────────────────────\n"

if [ "$FIXES" -gt 0 ]; then
    printf "  ${CYAN}%d item(s) auto-fixed${RESET}\n" "$FIXES"
fi
if [ "$WARNINGS" -gt 0 ]; then
    printf "  ${YELLOW}%d warning(s) require manual attention${RESET}\n" "$WARNINGS"
fi
if [ "$FAILURES" -gt 0 ]; then
    printf "  ${RED}%d item(s) failed — see details above${RESET}\n" "$FAILURES"
fi
if [ "$FAILURES" -eq 0 ] && [ "$WARNINGS" -eq 0 ] && [ "$FIXES" -eq 0 ]; then
    printf "  ${GREEN}All checks passed — nothing to do.${RESET}\n"
fi

printf "${BOLD}════════════════════════════════════════════════════════════════${RESET}\n"
printf "\n"

# Exit with non-zero if anything failed
[ "$FAILURES" -eq 0 ]
