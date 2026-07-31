#!/usr/bin/env python3
"""
FishCam System Monitor

Live dashboard showing the status of all FishCam processes, recent log
activity, hardware health, storage, and system state. Designed to run
over SSH — no display hardware required.

Usage (from the scripts directory):
    python3 monitor_system.py

Controls:
    r / R    — force immediate refresh
    q / Esc  — quit
"""

import curses
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import config


# ── Constants ─────────────────────────────────────────────────────────────────

REFRESH_INTERVAL = 10   # seconds between auto-refreshes

PROCESSES = [
    ('run_video.py',         'Video'),
    ('run_imu.py',           'IMU'),
    ('run_buzzer.py',        'Buzzer'),
    ('run_power_manager.py', 'Power manager'),
]


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
_CAMERA_CACHE_TTL    = 60  # seconds — libcamera-hello is slow; don't run every cycle

_voltage_cache       = None   # float (V) or None
_voltage_cache_time  = 0.0
_VOLTAGE_CACHE_TTL   = 30     # seconds

def check_camera():
    """Return (ok: bool|None, detail: str).  None = indeterminate.

    Result is cached for _CAMERA_CACHE_TTL seconds because libcamera-hello
    takes several seconds to run and camera presence doesn't change at runtime.
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
    """Read WittyPi input voltage via utilities.sh. Result is cached for _VOLTAGE_CACHE_TTL s.

    Returns float (V) or None if the WittyPi is unreachable or utilities.sh is missing.
    """
    global _voltage_cache, _voltage_cache_time
    if _voltage_cache_time and (time.time() - _voltage_cache_time) < _VOLTAGE_CACHE_TTL:
        return _voltage_cache

    voltage = None
    try:
        r = subprocess.run(
            ['bash', '-c',
             f'source "{install_dir}/utilities.sh" && '
             f'echo $(i2c_read 0x01 $I2C_MC_ADDRESS $I2C_CONF_VIN)'],
            capture_output=True, text=True, timeout=5, cwd=str(install_dir)
        )
        if r.returncode == 0:
            raw = r.stdout.strip()
            if raw:
                voltage = int(raw, 0) / 10.0
    except Exception:
        pass

    _voltage_cache      = voltage
    _voltage_cache_time = time.time()
    return voltage


def check_i2c(address):
    """Return (ok: bool|None, detail: str). Probe is read-only and non-destructive."""
    try:
        r = subprocess.run(['i2cdetect', '-y', '1'],
                           capture_output=True, text=True, timeout=5)
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
        # Disk usage for the filesystem that holds the data directory
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


# ── Data collection ───────────────────────────────────────────────────────────

def collect(script_dir, fishcam_id, paths, imu_cfg, wittypi_cfg):
    now = time.time()
    data = {'time': datetime.now(), 'fishcam_id': fishcam_id}

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

    return data


# ── Rendering ─────────────────────────────────────────────────────────────────

def put(stdscr, row, col, text, attr, W):
    max_rows, _ = stdscr.getmaxyx()
    if row >= max_rows - 1:
        return
    try:
        stdscr.addstr(row, col, str(text)[:max(0, W - col)], attr)
    except curses.error:
        pass


def render(stdscr, data, secs_to_refresh, C):
    stdscr.erase()
    _, W = stdscr.getmaxyx()
    r = 0

    def p(row, col, text, attr=0):
        put(stdscr, row, col, text, attr, W)

    def hr(row):
        p(row, 0, '─' * W)

    BOLD   = curses.A_BOLD
    GREEN  = C['green']
    RED    = C['red']
    YELLOW = C['yellow']
    CYAN   = C['cyan']

    # ── Header ──────────────────────────────────────────────────────────────
    ts = data['time'].strftime('%Y-%m-%d  %H:%M:%S')
    p(r, 0, '═' * W, BOLD); r += 1
    p(r, 0, f'  FishCam System Monitor  │  {data["fishcam_id"]}  │  {ts}  │  [r]efresh  [q]uit', BOLD | CYAN); r += 1
    p(r, 0, '═' * W, BOLD); r += 1

    # ── Processes ────────────────────────────────────────────────────────────
    p(r, 0, '  PROCESSES', BOLD); r += 1
    hr(r); r += 1

    for proc in data['processes']:
        label = f'  {proc["label"]:<18}'
        p(r, 0, label, BOLD)
        if proc['running']:
            p(r, len(label), f'✓ RUNNING   PID {proc["pid"]:<7} up {proc["uptime"]}', GREEN | BOLD)
        else:
            p(r, len(label), '✗ STOPPED', RED | BOLD)
        r += 1

    # ── Log activity ─────────────────────────────────────────────────────────
    p(r, 0, '  RECENT LOG ACTIVITY', BOLD); r += 1
    hr(r); r += 1

    LOG_LABELS = {
        'video':         'video        ',
        'imu':           'imu          ',
        'buzzer':        'buzzer       ',
        'power_manager': 'power_manager',
        'network':       'network      ',
        'voltage':       'voltage      ',
    }
    for lg in data['logs']:
        label = LOG_LABELS[lg['name']]
        prefix = f'  {label}: '
        p(r, 0, prefix, BOLD)

        if not lg['exists']:
            p(r, len(prefix), '(no log file yet)', YELLOW)
        elif lg['last_line'] is None:
            p(r, len(prefix), '(empty)', YELLOW)
        else:
            # Trim line to fit; show error badge at right margin
            badge = f' [{lg["err_1h"]} err/1h]' if lg['err_1h'] > 0 else ''
            max_len = W - len(prefix) - len(badge) - 1
            line = lg['last_line']
            if len(line) > max_len:
                line = '…' + line[-(max_len - 1):]
            attr = RED if lg['is_error'] else 0
            p(r, len(prefix), line, attr)
            if badge:
                p(r, W - len(badge) - 1, badge, RED | BOLD)
        r += 1

    # ── Hardware & System ────────────────────────────────────────────────────
    p(r, 0, '  HARDWARE & SYSTEM', BOLD); r += 1
    hr(r); r += 1

    cam_ok, cam_detail = data['camera']
    cam_sym  = '✓' if cam_ok else ('?' if cam_ok is None else '✗')
    cam_attr = GREEN if cam_ok else (YELLOW if cam_ok is None else RED)

    imu_ok, imu_detail = data['imu_bus']
    imu_sym  = '✓' if imu_ok else ('?' if imu_ok is None else '✗')
    imu_attr = GREEN if imu_ok else (YELLOW if imu_ok is None else RED)

    # Camera and I2C/IMU on one line
    cam_str = f'  Camera: {cam_sym} {cam_detail}'
    imu_str = f'I2C/IMU: {imu_sym} {imu_detail}'
    p(r, 0,        cam_str, cam_attr)
    p(r, max(len(cam_str) + 4, 32), imu_str, imu_attr)
    r += 1

    # Voltage
    v      = data['voltage']
    low_v  = data['voltage_low_v']
    rec_v  = data['voltage_rec_v']
    if v is not None:
        v_str = f'  Voltage: {v:.1f} V'
        if low_v > 0 and v < low_v:
            v_attr = RED | BOLD
        elif rec_v > 0 and v < rec_v:
            v_attr = YELLOW | BOLD
        else:
            v_attr = GREEN
    else:
        v_str  = '  Voltage: n/a'
        v_attr = YELLOW
    thresh_str = f'(cutoff {low_v} V / recovery {rec_v} V)' if low_v > 0 else '(protection disabled)'
    p(r, 0, v_str, v_attr)
    p(r, max(len(v_str) + 2, 22), thresh_str)
    r += 1

    # CPU temp + freq + uptime
    temp = data['cpu_temp']
    freq = data['cpu_freq']
    temp_str = f'  CPU: {temp:.1f}°C' if temp is not None else '  CPU: n/a'
    freq_str = f'{freq} MHz' if freq is not None else ''
    up_str   = f'Uptime: {data["uptime"]}'
    temp_attr = RED if (temp is not None and temp > 80) else \
                YELLOW if (temp is not None and temp > 70) else GREEN
    p(r, 0,  temp_str, temp_attr | BOLD)
    p(r, max(len(temp_str) + 2, 20), freq_str)
    p(r, max(len(temp_str) + len(freq_str) + 6, 34), up_str)
    r += 1

    # WiFi + disk
    st = data['storage']
    wifi_str = f'  WiFi: {data["wifi"]}'
    if st['total_gb'] is not None:
        disk_str = f'Disk: {st["used_gb"]:.1f}/{st["total_gb"]:.0f} GB ({st["pct"]:.0f}%)'
        disk_attr = RED if st['pct'] > 90 else (YELLOW if st['pct'] > 75 else GREEN)
    else:
        disk_str = 'Disk: unavailable'
        disk_attr = YELLOW
    vid_str = f'Video: {st["video_count"]} files' if st['video_count'] is not None else ''

    p(r, 0, wifi_str)
    p(r, max(len(wifi_str) + 2, 30), disk_str, disk_attr)
    p(r, max(len(wifi_str) + len(disk_str) + 6, 56), vid_str)
    r += 1

    # ── Footer ───────────────────────────────────────────────────────────────
    p(r, 0, '═' * W, BOLD); r += 1
    p(r, 0, f'  Refreshing in {secs_to_refresh}s', CYAN)

    stdscr.refresh()


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_monitor(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN,  -1)
    curses.init_pair(2, curses.COLOR_RED,    -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN,   -1)
    C = {
        'green':  curses.color_pair(1),
        'red':    curses.color_pair(2),
        'yellow': curses.color_pair(3),
        'cyan':   curses.color_pair(4),
    }

    script_dir  = Path(__file__).parent
    fishcam_id  = config.get_fishcam_id()
    paths       = config.get_paths()
    imu_cfg     = config.get_imu_settings()
    wittypi_cfg = config.get_wittypi_settings()

    last_refresh = 0.0
    data = None

    while True:
        now = time.monotonic()
        key = stdscr.getch()

        if key in (ord('q'), ord('Q'), 27):
            break

        force = key in (ord('r'), ord('R'))
        if force or (now - last_refresh) >= REFRESH_INTERVAL:
            data = collect(script_dir, fishcam_id, paths, imu_cfg, wittypi_cfg)
            last_refresh = time.monotonic()

        if data:
            secs_left = max(0, REFRESH_INTERVAL - int(time.monotonic() - last_refresh))
            render(stdscr, data, secs_left, C)

        time.sleep(0.25)


def main():
    try:
        config.get_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    try:
        curses.wrapper(run_monitor)
    except KeyboardInterrupt:
        pass

    print("Monitor stopped.")


if __name__ == '__main__':
    main()
