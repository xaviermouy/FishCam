#!/usr/bin/env python3
"""
FishCam System Status

Shared data-collection module used by both monitor_system.py (curses dashboard)
and run_api.py (HTTP API).  All functions that read hardware / processes / logs
live here so both consumers get identical data.
"""

import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from wittypi_utils import read_wittypi_voltage as _read_wittypi_voltage
from buzzer_utils import get_buzzer_status


# ── Constants ─────────────────────────────────────────────────────────────────

PROCESSES = [
    ('run_video.py',         'Video'),
    ('run_imu.py',           'IMU'),
    ('run_buzzer.py',        'Buzzer'),
    ('run_power_manager.py', 'Power manager'),
]

# Age threshold (seconds) for deciding whether an acquisition file is "active"
_ACTIVE_FILE_MAX_AGE_S = 120


# ── Process detection ─────────────────────────────────────────────────────────

_boot_time_cache = None


def _boot_time():
    global _boot_time_cache
    if _boot_time_cache is None:
        with open('/proc/stat') as f:
            for line in f:
                if line.startswith('btime'):
                    _boot_time_cache = int(line.split()[1])
                    break
    return _boot_time_cache


def find_process(script_name):
    """Return (pid, start_epoch) if script_name appears in any /proc cmdline, else None."""
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / 'cmdline').read_bytes().replace(b'\x00', b' ').decode(errors='replace')
            if script_name in cmdline:
                pid = int(entry.name)
                stat = (entry / 'stat').read_text().split()
                start_ticks = int(stat[21])
                clk_tck = os.sysconf('SC_CLK_TCK')
                start_epoch = _boot_time() + start_ticks / clk_tck
                return pid, start_epoch
        except (PermissionError, FileNotFoundError, ValueError, IndexError):
            continue
    return None


def fmt_uptime(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d > 0:
        return f'{d}d {h}h {m}m'
    if h > 0:
        return f'{h}h {m}m'
    return f'{m}m'


# ── Log reading ───────────────────────────────────────────────────────────────

def tail_bytes(path, nbytes=8192):
    """Return last nbytes of a file as a list of lines."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            f.seek(-min(size, nbytes), 2)
            return f.read().decode(errors='replace').splitlines()
    except (FileNotFoundError, OSError):
        return []


def last_notable(lines):
    """Return (line, is_error): last ERROR/WARNING line, or last non-empty line."""
    for line in reversed(lines):
        if 'ERROR' in line or 'WARNING' in line:
            return line.strip(), True
    for line in reversed(lines):
        if line.strip():
            return line.strip(), False
    return None, False


def count_recent_errors(lines, minutes=60):
    """Count ERROR/WARNING lines whose timestamp falls within the last `minutes`."""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    count = 0
    for line in lines:
        if 'ERROR' not in line and 'WARNING' not in line:
            continue
        try:
            ts = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f')
            if ts >= cutoff:
                count += 1
        except ValueError:
            pass
    return count


# ── Hardware checks ───────────────────────────────────────────────────────────

_camera_cache        = None
_camera_cache_time   = 0.0
_CAMERA_CACHE_TTL    = 60   # seconds

_voltage_cache       = None
_voltage_cache_time  = 0.0
_VOLTAGE_CACHE_TTL   = 30   # seconds


def check_camera():
    """Return (ok: bool|None, detail: str).

    Cached for _CAMERA_CACHE_TTL seconds because libcamera-hello is slow.
    """
    global _camera_cache, _camera_cache_time
    if _camera_cache is not None and (time.time() - _camera_cache_time) < _CAMERA_CACHE_TTL:
        return _camera_cache

    try:
        r = subprocess.run(['libcamera-hello', '--list-cameras'],
                           capture_output=True, text=True, timeout=5)
        out = (r.stdout + r.stderr).strip()
        if 'Available cameras' in out and '0 :' in out:
            result = True, 'Detected'
        elif 'No cameras available' in out:
            result = False, 'Not detected'
        else:
            result = None, 'Unknown'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        if list(Path('/dev').glob('video*')):
            result = True, '/dev/video* present'
        else:
            result = None, 'libcamera unavailable'

    _camera_cache      = result
    _camera_cache_time = time.time()
    return result


def read_wittypi_voltage(install_dir):
    """Read WittyPi input voltage. Cached for _VOLTAGE_CACHE_TTL seconds."""
    global _voltage_cache, _voltage_cache_time
    if _voltage_cache_time and (time.time() - _voltage_cache_time) < _VOLTAGE_CACHE_TTL:
        return _voltage_cache

    voltage             = _read_wittypi_voltage(install_dir)
    _voltage_cache      = voltage
    _voltage_cache_time = time.time()
    return voltage


def check_i2c(address):
    """Return (ok: bool|None, detail: str). Probe is read-only and non-destructive."""
    try:
        env = os.environ.copy()
        env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:' + env.get('PATH', '')
        r = subprocess.run(['i2cdetect', '-y', '1'],
                           capture_output=True, text=True, timeout=5, env=env)
        addr_hex = f'{address:02x}'
        if addr_hex in r.stdout.lower():
            return True, f'0x{address:02X} on bus 1'
        return False, f'0x{address:02X} not found on bus 1'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, 'i2cdetect unavailable'


# ── System info ───────────────────────────────────────────────────────────────

def cpu_temp():
    try:
        r = subprocess.run(['vcgencmd', 'measure_temp'],
                           capture_output=True, text=True, timeout=2)
        return float(r.stdout.strip().split('=')[1].replace("'C", ''))
    except Exception:
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                return int(f.read()) / 1000.0
        except Exception:
            return None


def cpu_freq_mhz():
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq') as f:
            return int(f.read().strip()) // 1000
    except Exception:
        return None


def wifi_status():
    try:
        radio = subprocess.run(['nmcli', 'radio', 'wifi'],
                               capture_output=True, text=True, timeout=2).stdout.strip()
        if radio != 'enabled':
            return 'Disabled'
        conn = subprocess.run(
            ['nmcli', '-t', '-f', 'GENERAL.CONNECTION', 'dev', 'show', 'wlan0'],
            capture_output=True, text=True, timeout=2
        ).stdout.strip().split(':')[-1]
        return f'Connected ({conn})' if conn and conn != '--' else 'Enabled, not connected'
    except Exception:
        return 'Unknown'


def system_uptime():
    try:
        with open('/proc/uptime') as f:
            return fmt_uptime(float(f.read().split()[0]))
    except Exception:
        return 'Unknown'


# ── Storage ───────────────────────────────────────────────────────────────────

def storage_info(paths, script_dir):
    info = {}
    try:
        data_root = (script_dir / paths['video_dir']).parent
        u = shutil.disk_usage(data_root)
        info['total_gb'] = u.total / 1e9
        info['used_gb']  = u.used  / 1e9
        info['free_gb']  = u.free  / 1e9
        info['pct']      = 100.0 * u.used / u.total
    except Exception:
        info.update(total_gb=None, used_gb=None, free_gb=None, pct=None)

    for key, rel, globs in [
        ('video_count', paths['video_dir'], ('*.h264', '*.mjpeg')),
        ('imu_count',   paths['imu_dir'],   ('*.csv',)),
    ]:
        try:
            d = script_dir / rel
            if d.is_dir():
                count = sum(len(list(d.rglob(pat))) for pat in globs)
                info[key] = count
            else:
                info[key] = 0
        except Exception:
            info[key] = None

    return info


# ── Acquisition status ────────────────────────────────────────────────────────

def acquisition_status(paths, script_dir):
    """Return acquisition activity for video and IMU.

    A file is considered "active" if its mtime is within _ACTIVE_FILE_MAX_AGE_S
    seconds of now.

    Returns:
        dict with 'video' and 'imu' keys, each:
            {active: bool, last_file: str or None, age_s: int or None}
    """
    result = {}
    now = time.time()

    checks = [
        ('video', paths['video_dir'], ('*.h264', '*.mjpeg')),
        ('imu',   paths['imu_dir'],   ('*.csv',)),
    ]

    for key, rel_dir, globs in checks:
        d = script_dir / rel_dir
        newest_mtime = None
        newest_name  = None

        if d.is_dir():
            for pat in globs:
                for f in d.rglob(pat):
                    try:
                        mt = f.stat().st_mtime
                        if newest_mtime is None or mt > newest_mtime:
                            newest_mtime = mt
                            newest_name  = f.name
                    except OSError:
                        pass

        if newest_mtime is not None:
            age_s  = int(now - newest_mtime)
            active = age_s <= _ACTIVE_FILE_MAX_AGE_S
        else:
            age_s  = None
            active = False

        result[key] = {
            'active':    active,
            'last_file': newest_name,
            'age_s':     age_s,
        }

    return result


# ── IMU latest reading ────────────────────────────────────────────────────────

def imu_latest_reading(paths, script_dir):
    """Return the most recent IMU sample from the latest CSV written by run_imu.py.

    Reads only the header row and the last data row — no sensor hardware access.
    Returns a dict with orientation, sensor vectors, and data age, or None if no
    CSV exists yet or the file contains only a header.
    """
    imu_dir = script_dir / paths['imu_dir']
    try:
        candidates = list(Path(imu_dir).glob('*.csv'))
        if not candidates:
            return None
        csv_path = max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:
        return None

    try:
        with open(csv_path, 'rb') as f:
            header_line = f.readline().decode().strip()
            if not header_line:
                return None
            try:
                f.seek(-2, 2)
            except OSError:
                return None                      # file too small — header only
            while f.read(1) != b'\n':
                try:
                    f.seek(-2, 1)
                except OSError:
                    return None
            data_line = f.readline().decode().strip()
        if not data_line:
            return None
    except Exception:
        return None

    cols = header_line.split(',')
    vals = data_line.split(',')
    row  = dict(zip(cols, vals))

    def get(key):
        try:
            v = row.get(key, '').strip()
            return float(v) if v else None
        except (ValueError, AttributeError):
            return None

    try:
        age_s = int(time.time() - csv_path.stat().st_mtime)
    except Exception:
        age_s = None

    result = {
        'age_s':   age_s,
        'heading': get('heading_deg'),
        'pitch':   get('pitch_deg'),
        'roll':    get('roll_deg'),
    }
    for key, col_names in [
        ('accel', ['accel_x_ms2',     'accel_y_ms2',     'accel_z_ms2']),
        ('gyro',  ['gyro_x_rads',     'gyro_y_rads',     'gyro_z_rads']),
        ('mag',   ['mag_x_uT',        'mag_y_uT',        'mag_z_uT']),
        ('lin',   ['lin_accel_x_ms2', 'lin_accel_y_ms2', 'lin_accel_z_ms2']),
        ('grav',  ['gravity_x_ms2',   'gravity_y_ms2',   'gravity_z_ms2']),
    ]:
        result[key] = [get(c) for c in col_names] if all(c in row for c in col_names) else None

    return result


# ── Data collection ───────────────────────────────────────────────────────────

def collect(script_dir, fishcam_id, paths, imu_cfg, wittypi_cfg, buzzer_cfg):
    """Collect all system status data.

    Args:
        script_dir:  Path to the scripts directory
        fishcam_id:  Hostname / ID string
        paths:       dict from config.get_paths()
        imu_cfg:     dict from config.get_imu_settings()
        wittypi_cfg: dict from config.get_wittypi_settings()
        buzzer_cfg:  dict from config.get_buzzer_settings()

    Returns:
        dict suitable for rendering (monitor_system) or JSON serialisation (run_api).
        data['time'] is a string '%Y-%m-%d %H:%M:%S' (not a datetime object).
    """
    now = time.time()
    data = {
        'time':       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fishcam_id': fishcam_id,
    }

    # Processes
    data['processes'] = []
    for script, label in PROCESSES:
        proc = find_process(script)
        if proc:
            pid, start = proc
            data['processes'].append({
                'label': label, 'running': True,
                'pid': pid, 'uptime': fmt_uptime(now - start),
            })
        else:
            data['processes'].append({
                'label': label, 'running': False,
                'pid': None, 'uptime': None,
            })

    # Logs
    log_dir = script_dir / paths['log_dir']
    log_sources = [
        ('video',         log_dir / f'video_{fishcam_id}.log'),
        ('imu',           log_dir / f'imu_{fishcam_id}.log'),
        ('buzzer',        log_dir / f'buzzer_{fishcam_id}.log'),
        ('power_manager', log_dir / f'power_saving_{fishcam_id}.log'),
        ('network',       log_dir / f'network_{fishcam_id}.log'),
        ('voltage',       log_dir / f'voltage_{fishcam_id}.csv'),
    ]
    data['logs'] = []
    for name, path in log_sources:
        lines = tail_bytes(path)
        last_line, is_err = last_notable(lines)
        err_1h = count_recent_errors(lines)
        data['logs'].append({
            'name': name, 'exists': path.exists(),
            'last_line': last_line, 'is_error': is_err,
            'err_1h': err_1h,
        })

    # Hardware
    data['camera']   = check_camera()
    data['imu_bus']  = check_i2c(imu_cfg['i2c_address'])
    data['imu_addr'] = imu_cfg['i2c_address']
    data['voltage']  = read_wittypi_voltage(wittypi_cfg['install_dir'])
    data['voltage_low_v'] = wittypi_cfg['low_voltage_cutoff_v']
    data['voltage_rec_v'] = wittypi_cfg['recovery_voltage_v']

    # System
    data['cpu_temp'] = cpu_temp()
    data['cpu_freq'] = cpu_freq_mhz()
    data['wifi']     = wifi_status()
    data['uptime']   = system_uptime()

    # Storage
    data['storage'] = storage_info(paths, script_dir)

    # Acquisition activity
    data['acquisition'] = acquisition_status(paths, script_dir)

    # Buzzer schedule
    buzzer_log = log_dir / f'buzzer_{fishcam_id}.log'
    data['buzzer'] = get_buzzer_status(buzzer_cfg, buzzer_log)

    # IMU latest reading (from CSV — no hardware access)
    data['imu_data'] = imu_latest_reading(paths, script_dir)

    return data
