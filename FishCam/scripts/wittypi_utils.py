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
    ok, out = run_wittypi_func(install_dir, 'system_to_rtc')
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    if ok:
        return True, f"WittyPi RTC synced from system clock  ({now_str} UTC)"
    return False, f"system_to_rtc failed: {out}"


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
    """Read WittyPi input voltage via utilities.sh.

    Reads the raw Vin register using WittyPi's own i2c_read function.
    The Vin calibration adjustment (set via WittyPi menu > other settings >
    Vin adjustment) is only applied in wittyPi.sh, not in utilities.sh, so
    it cannot be retrieved here. The raw reading may differ from the WittyPi
    menu display by the configured adjustment offset (typically ~0.2 V).

    Returns:
        float: voltage in volts, or None if the read fails (WittyPi not
               connected, utilities.sh missing, I2C error, etc.)
    """
    bash_cmd = (
        'vin=$(i2c_read 0x01 $I2C_MC_ADDRESS $I2C_CONF_VIN) && '
        'awk "BEGIN{printf \\"%.1f\\", $vin/10}"'
    )
    try:
        ok, out = run_wittypi_func(install_dir, bash_cmd)
        if ok and out.strip():
            return float(out.strip())
    except Exception:
        pass
    return None
