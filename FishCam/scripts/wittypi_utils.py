"""
FishCam WittyPi Utility Functions

Low-level helpers shared across FishCam scripts that interact with the
WittyPi hardware. Kept separate so that configure_wittypi.py (setup),
sync_rtc.py (boot-time NTP sync), run_gps.py (GPS sync), and
monitor_system.py / run_power_manager.py (voltage reading) can all
import from one place without circular dependencies.
"""

import os
import pwd
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# ── WittyPi bash interface ────────────────────────────────────────────────────

def run_wittypi_func(install_dir, bash_cmd):
    """Source utilities.sh and run a WittyPi bash function.

    Args:
        install_dir: Path to the WittyPi installation directory.
        bash_cmd:    Bash command to run after sourcing utilities.sh.

    Returns:
        (ok: bool, output: str)

    When called from a root process (e.g. run_power_manager.py runs under
    sudo), the bash command is re-executed as the owner of install_dir via
    'sudo -u <owner>'.  This prevents utilities.sh from creating root-owned
    wittyPi.log entries that would block later runs by the fishcam user.
    """
    full_cmd = f'source "{install_dir}/utilities.sh" && {bash_cmd}'
    cmd = ['bash', '-c', full_cmd]

    if os.getuid() == 0:
        # Running as root — drop to the install_dir owner so log writes
        # stay owned by that user (normally 'fishcam').
        try:
            dir_uid = os.stat(install_dir).st_uid
            if dir_uid != 0:
                dir_owner = pwd.getpwuid(dir_uid).pw_name
                cmd = ['sudo', '-u', dir_owner, 'bash', '-c', full_cmd]
        except (OSError, KeyError):
            pass  # can't determine owner — fall back to running as root

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(install_dir))
    return r.returncode == 0, (r.stdout + r.stderr).strip()


# ── NTP helpers ──────────────────────────────────────────────────────────────

def is_wifi_up():
    """Return True if the wlan0 interface is up and associated."""
    try:
        return (Path('/sys/class/net/wlan0/operstate')
                .read_text().strip() == 'up')
    except OSError:
        return False


def is_ntp_synced():
    """Return True if timedatectl reports the system clock as NTP-synchronized."""
    try:
        r = subprocess.run(
            ['timedatectl', 'show', '--property=NTPSynchronized', '--value'],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip().lower() == 'yes'
    except Exception:
        return False


# ── RTC sync ──────────────────────────────────────────────────────────────────

def sync_rtc_from_system(install_dir):
    """Push the current system clock to the WittyPi RTC via utilities.sh.

    Uses WittyPi's own system_to_rtc() function so that all I2C
    communication goes through the WittyPi microcontroller — no
    hardcoded register addresses needed.

    This function is intentionally source-agnostic: the caller is
    responsible for ensuring the system clock is accurate before calling
    (e.g. NTP synced, or GPS time applied). It can be called from:
      - configure_wittypi.py  : manual pre-deployment sync
      - sync_rtc.py           : automatic NTP sync at boot
      - run_gps.py            : automatic GPS sync at runtime (future)

    Returns:
        (ok: bool, message: str)
    """
    _, out = run_wittypi_func(install_dir, 'system_to_rtc')
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    # Use "Done" in output as the success indicator rather than exit code —
    # a root-owned wittyPi.log causes a non-zero exit even when the I2C
    # write itself succeeded.
    if 'Done' in out:
        return True, f"WittyPi RTC synced from system clock  ({now_str} UTC)"
    return False, f"system_to_rtc failed: {out}"


def sync_rtc_from_ntp(install_dir):
    """Sync internet time to system clock, then push system clock to WittyPi RTC.

    Uses WittyPi's own net_to_system() which fetches the current time from
    Google's HTTP Date header (no NTP daemon required, no chrony dependency).
    Falls back gracefully if internet is unreachable — the RTC is still
    updated from the current system clock with a warning.

    Returns:
        (ntp_ok: bool, ntp_msg: str, rtc_ok: bool, rtc_msg: str)
        ntp_ok=False is a warning (not fatal) — RTC sync is always attempted.
        rtc_ok=False means the RTC write itself failed and is fatal.
    """
    _, out = run_wittypi_func(install_dir, 'net_to_system')
    # Use "Done" in output as the success indicator rather than exit code —
    # a root-owned wittyPi.log causes a non-zero exit even when the curl
    # time fetch itself succeeded.
    if 'Done' in out:
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        ntp_ok  = True
        ntp_msg = f"Network time applied to system clock  ({now_str} UTC)"
    else:
        ntp_ok  = False
        ntp_msg = f"Could not get network time — system clock unchanged  ({out.strip()})"

    rtc_ok, rtc_msg = sync_rtc_from_system(install_dir)
    return ntp_ok, ntp_msg, rtc_ok, rtc_msg


# ── RTC sync state file ───────────────────────────────────────────────────────

_RTC_SYNC_STATE_FILE = 'last_rtc_sync.txt'
_RTC_SYNC_TIME_FMT   = '%Y-%m-%d %H:%M:%S'


def get_rtc_sync_state_path(log_dir):
    """Return the path to the RTC sync state file in log_dir."""
    return Path(log_dir) / _RTC_SYNC_STATE_FILE


def is_rtc_sync_due(state_file, min_interval_min):
    """Return True if enough time has passed since the last RTC sync.

    Returns True if the state file is missing or unreadable (i.e. never
    synced), or if the recorded time is older than min_interval_min.
    """
    try:
        text = Path(state_file).read_text().strip()
        last_sync = datetime.strptime(text, _RTC_SYNC_TIME_FMT)
        elapsed_min = (datetime.now() - last_sync).total_seconds() / 60
        return elapsed_min >= min_interval_min
    except (FileNotFoundError, ValueError):
        return True  # never synced or state file corrupt — sync is due


def record_rtc_sync(state_file):
    """Write the current timestamp to the RTC sync state file."""
    Path(state_file).write_text(datetime.now().strftime(_RTC_SYNC_TIME_FMT))


# ── Voltage reading ───────────────────────────────────────────────────────────

def read_wittypi_voltage(install_dir):
    """Read WittyPi input voltage via utilities.sh get_input_voltage().

    Returns:
        float: voltage in volts, or None if the read fails (WittyPi not
               connected, utilities.sh missing, I2C error, etc.)
    """
    import re
    try:
        _, out = run_wittypi_func(install_dir, 'get_input_voltage')
        # Don't rely on exit code — a root-owned wittyPi.log causes non-zero
        # exit even when the I2C read itself succeeded.  Extract the first
        # decimal number from the output regardless (handles "5.12", "Vin:
        # 5.12 V", "Input voltage: 5.12V", etc.).
        match = re.search(r'\d+\.\d+', out)
        if match:
            return float(match.group())
    except Exception:
        pass
    return None
