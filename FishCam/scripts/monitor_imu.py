#!/usr/bin/env python3
"""
FishCam IMU Monitor  (Testing Utility)

Real-time terminal display of BNO085 IMU data for testing and verification.
Designed to run over SSH — no screen or display hardware required.

If run_imu.py is already running, the monitor reads from its live CSV file
instead of accessing the I2C bus directly, avoiding conflicts.

Usage (from the scripts directory):
    python3 monitor_imu.py

Controls:
    q / Q / Esc  — quit

Source modes (shown in header):
    direct sensor  — monitor has exclusive I2C access
    live recording — run_imu.py is running; values read from its CSV
    waiting        — run_imu.py is running but no CSV data yet
"""

import curses
import math
import subprocess
import sys
import time
from pathlib import Path

import config
import board
import busio
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_ROTATION_VECTOR,
    BNO_REPORT_LINEAR_ACCELERATION,
    BNO_REPORT_GRAVITY,
)
from adafruit_bno08x.i2c import BNO08X_I2C


# ── Helpers ────────────────────────────────────────────────────────────────────

def quat_to_euler(i, j, k, real):
    """Convert quaternion to (yaw, pitch, roll) in degrees.

    Yaw is referenced to magnetic north, normalised to 0–360°.
    """
    yaw   = math.degrees(math.atan2(2*(real*k + i*j), 1 - 2*(j**2 + k**2)))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, 2*(real*j - k*i)))))
    roll  = math.degrees(math.atan2(2*(real*i + j*k), 1 - 2*(i**2 + j**2)))
    return yaw % 360, pitch, roll


def fmt_float(value, width=8, decimals=3):
    """Format a float with sign and fixed decimals, or '---' if None."""
    if value is None:
        return '---'.rjust(width)
    return f'{value:+{width}.{decimals}f}'


def fmt_angle(value, width=7, decimals=1):
    """Format an angle in degrees, or '---' if None."""
    if value is None:
        return '---'.rjust(width)
    return f'{value:{width}.{decimals}f}'


# ── Source detection ───────────────────────────────────────────────────────────

def is_run_imu_active():
    """Return True if run_imu.py is currently running."""
    r = subprocess.run(['pgrep', '-f', 'run_imu.py'],
                       capture_output=True, text=True)
    return r.returncode == 0


# ── CSV reading ────────────────────────────────────────────────────────────────

def _find_latest_csv(imu_dir):
    """Return the most recently modified .csv file in imu_dir, or None."""
    candidates = list(Path(imu_dir).glob('*.csv'))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _read_last_line(path):
    """Return the last non-empty line of a file, or None if only header exists."""
    with open(path, 'rb') as f:
        # Read header
        header_line = f.readline().decode().strip()
        if not header_line:
            return None, None

        # Seek to near end and walk back to find last complete line
        try:
            f.seek(-2, 2)
        except OSError:
            return header_line, None  # file too small — only header

        while f.read(1) != b'\n':
            try:
                f.seek(-2, 1)
            except OSError:
                return header_line, None  # still only header

        last = f.readline().decode().strip()
        return header_line, last if last else None


def _parse_float(s):
    """Parse a CSV float string, returning None if empty or invalid."""
    try:
        return float(s) if s.strip() else None
    except ValueError:
        return None


def read_csv_sample(imu_dir):
    """Read the latest sample from the most recent IMU CSV.

    Returns a data dict (see read_sensor_sample for format), or None if no
    CSV exists yet or the file contains only a header row.
    """
    csv_path = _find_latest_csv(imu_dir)
    if csv_path is None:
        return None

    try:
        header_line, data_line = _read_last_line(csv_path)
    except OSError:
        return None

    if not data_line:
        return None

    cols   = header_line.split(',')
    values = data_line.split(',')
    row    = dict(zip(cols, values))

    def get(key):
        return _parse_float(row.get(key, ''))

    # Quaternion → Euler
    qi, qj, qk, qr = get('quat_i'), get('quat_j'), get('quat_k'), get('quat_real')
    if all(v is not None for v in (qi, qj, qk, qr)):
        quat = (qi, qj, qk, qr)
        yaw  = get('heading_deg')
        pitch = get('pitch_deg')
        roll  = get('roll_deg')
    else:
        quat = yaw = pitch = roll = None

    accel = (get('accel_x_ms2'), get('accel_y_ms2'), get('accel_z_ms2')) \
            if 'accel_x_ms2' in row else None
    gyro  = (get('gyro_x_rads'), get('gyro_y_rads'), get('gyro_z_rads')) \
            if 'gyro_x_rads' in row else None
    mag   = (get('mag_x_uT'), get('mag_y_uT'), get('mag_z_uT')) \
            if 'mag_x_uT' in row else None
    lin   = (get('lin_accel_x_ms2'), get('lin_accel_y_ms2'), get('lin_accel_z_ms2')) \
            if 'lin_accel_x_ms2' in row else None
    grav  = (get('gravity_x_ms2'), get('gravity_y_ms2'), get('gravity_z_ms2')) \
            if 'gravity_x_ms2' in row else None

    cal_raw = row.get('calibration_status', '').strip()
    cal = int(cal_raw) if cal_raw.isdigit() else None

    return {
        'source': 'recording',
        'accel': accel, 'gyro': gyro, 'mag': mag,
        'quat': quat, 'yaw': yaw, 'pitch': pitch, 'roll': roll,
        'lin': lin, 'grav': grav,
        'calibration_status': cal,
    }


# ── IMU setup & direct sensor reading ─────────────────────────────────────────

def setup_imu(imu_cfg, max_attempts=5, retry_delay=2.0):
    """Initialise I2C bus and BNO085, enabling all configured reports."""
    interval_us = int(1_000_000 / imu_cfg['sample_rate_hz'])
    i2c = busio.I2C(board.SCL, board.SDA)

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            imu = BNO08X_I2C(i2c, address=imu_cfg['i2c_address'])
            if imu_cfg['accelerometer']:
                imu.enable_feature(BNO_REPORT_ACCELEROMETER,       report_interval=interval_us)
            if imu_cfg['gyroscope']:
                imu.enable_feature(BNO_REPORT_GYROSCOPE,           report_interval=interval_us)
            if imu_cfg['magnetometer']:
                imu.enable_feature(BNO_REPORT_MAGNETOMETER,        report_interval=interval_us)
            if imu_cfg['rotation_vector']:
                imu.enable_feature(BNO_REPORT_ROTATION_VECTOR,     report_interval=interval_us)
            if imu_cfg['linear_acceleration']:
                imu.enable_feature(BNO_REPORT_LINEAR_ACCELERATION, report_interval=interval_us)
            if imu_cfg['gravity']:
                imu.enable_feature(BNO_REPORT_GRAVITY,             report_interval=interval_us)
            return imu
        except Exception as e:
            last_error = e
            print(f"IMU init attempt {attempt}/{max_attempts} failed: {e} — retrying in {retry_delay}s...")
            time.sleep(retry_delay)

    raise RuntimeError(f"IMU failed to initialise after {max_attempts} attempts: {last_error}")


def read_sensor_sample(imu, imu_cfg):
    """Read one sample from the IMU and return a data dict."""
    accel = imu.acceleration        if imu_cfg['accelerometer']       else None
    gyro  = imu.gyro                if imu_cfg['gyroscope']           else None
    mag   = imu.magnetic            if imu_cfg['magnetometer']        else None
    quat  = imu.quaternion          if imu_cfg['rotation_vector']     else None
    lin   = imu.linear_acceleration if imu_cfg['linear_acceleration'] else None
    grav  = imu.gravity             if imu_cfg['gravity']             else None

    yaw = pitch = roll = None
    if quat is not None:
        qi, qj, qk, qr = quat
        if all(v is not None for v in (qi, qj, qk, qr)):
            yaw, pitch, roll = quat_to_euler(qi, qj, qk, qr)

    try:
        cal = imu.calibration_status if imu_cfg['rotation_vector'] else None
    except Exception:
        cal = None

    return {
        'source': 'sensor',
        'accel': accel, 'gyro': gyro, 'mag': mag,
        'quat': quat,   'yaw': yaw,   'pitch': pitch, 'roll': roll,
        'lin': lin,     'grav': grav,
        'calibration_status': cal,
    }


# ── Display ────────────────────────────────────────────────────────────────────

def draw(stdscr, data, imu_cfg, start_time, sample_count, actual_hz):
    """Render one frame from a data dict."""
    stdscr.erase()
    max_rows, max_cols = stdscr.getmaxyx()
    W = max_cols

    def put(row, text, bold=False):
        if row >= max_rows - 1:
            return
        attr = curses.A_BOLD if bold else curses.A_NORMAL
        try:
            stdscr.addstr(row, 0, text[:W], attr)
        except curses.error:
            pass

    source = data.get('source', 'sensor')
    source_label = {
        'sensor':    'direct sensor',
        'recording': 'live recording  (run_imu.py active — no I2C conflict)',
        'waiting':   'waiting for first sample  (run_imu.py active)',
    }.get(source, source)

    accel = data.get('accel')
    gyro  = data.get('gyro')
    mag   = data.get('mag')
    lin   = data.get('lin')
    grav  = data.get('grav')
    yaw   = data.get('yaw')
    pitch = data.get('pitch')
    roll  = data.get('roll')
    cal   = data.get('calibration_status')

    elapsed = time.monotonic() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)

    r = 0
    put(r, '═' * W); r += 1
    put(r, f'  FishCam IMU Monitor'
           f'  |  {imu_cfg["sample_rate_hz"]} Hz configured'
           f'  |  {actual_hz:.1f} Hz actual'
           f'  |  source: {source_label}', bold=True); r += 1
    put(r, '═' * W); r += 1

    if imu_cfg['rotation_vector']:
        _CAL_LABELS = {0: '0 - unreliable', 1: '1 - low', 2: '2 - medium', 3: '3 - high'}
        cal_str = _CAL_LABELS.get(cal, '---') if cal is not None else '---'
        r += 1
        put(r, '  Orientation', bold=True); r += 1
        put(r, f'    Heading (mag N) : {fmt_angle(yaw):>8}°'); r += 1
        put(r, f'    Pitch           : {fmt_angle(pitch):>8}°'); r += 1
        put(r, f'    Roll            : {fmt_angle(roll):>8}°'); r += 1
        put(r, f'    Calibration     : {cal_str}'); r += 1

    if imu_cfg['accelerometer']:
        ax, ay, az = accel if accel is not None else (None, None, None)
        r += 1
        put(r, '  Accelerometer  (m/s²)', bold=True); r += 1
        put(r, f'    X: {fmt_float(ax)}   Y: {fmt_float(ay)}   Z: {fmt_float(az)}'); r += 1

    if imu_cfg['gyroscope']:
        gx, gy, gz = gyro if gyro is not None else (None, None, None)
        r += 1
        put(r, '  Gyroscope  (rad/s)', bold=True); r += 1
        put(r, f'    X: {fmt_float(gx)}   Y: {fmt_float(gy)}   Z: {fmt_float(gz)}'); r += 1

    if imu_cfg['magnetometer']:
        mx, my, mz = mag if mag is not None else (None, None, None)
        r += 1
        put(r, '  Magnetometer  (µT)', bold=True); r += 1
        put(r, f'    X: {fmt_float(mx)}   Y: {fmt_float(my)}   Z: {fmt_float(mz)}'); r += 1

    if imu_cfg['linear_acceleration']:
        lx, ly, lz = lin if lin is not None else (None, None, None)
        r += 1
        put(r, '  Linear Acceleration  (m/s², gravity removed)', bold=True); r += 1
        put(r, f'    X: {fmt_float(lx)}   Y: {fmt_float(ly)}   Z: {fmt_float(lz)}'); r += 1

    if imu_cfg['gravity']:
        grx, gry, grz = grav if grav is not None else (None, None, None)
        r += 1
        put(r, '  Gravity Vector  (m/s²)', bold=True); r += 1
        put(r, f'    X: {fmt_float(grx)}   Y: {fmt_float(gry)}   Z: {fmt_float(grz)}'); r += 1

    r += 1
    put(r, '─' * W); r += 1
    put(r, f'  Samples: {sample_count:<8}  Uptime: {h:02d}:{m:02d}:{s:02d}'
           f'  |  press q to quit'); r += 1
    put(r, '═' * W)

    stdscr.refresh()


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_monitor(stdscr, imu_cfg, imu_dir):
    """Curses main loop — auto-selects source based on whether run_imu.py is active."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    interval     = 1.0 / imu_cfg['sample_rate_hz']
    start_time   = time.monotonic()
    sample_count = 0

    hz_window_start = time.monotonic()
    hz_window_count = 0
    actual_hz       = 0.0

    imu          = None   # live I2C object (only when in sensor mode)
    current_mode = None   # 'sensor' or 'recording'

    while True:
        loop_start = time.monotonic()

        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break

        recording_active = is_run_imu_active()

        # ── Mode transitions ──────────────────────────────────────────────────
        if recording_active and current_mode != 'recording':
            # Switch to recording mode — release I2C if we held it
            if imu is not None:
                try:
                    imu._i2c.deinit()
                except Exception:
                    pass
                imu = None
            current_mode = 'recording'

        elif not recording_active and current_mode != 'sensor':
            # Switch to sensor mode — initialise I2C
            current_mode = 'sensor'
            try:
                imu = setup_imu(imu_cfg, max_attempts=3, retry_delay=1.0)
            except Exception:
                imu = None  # will show --- values until it recovers

        # ── Read data ─────────────────────────────────────────────────────────
        try:
            if current_mode == 'recording':
                data = read_csv_sample(imu_dir) or {'source': 'waiting'}
            else:
                data = read_sensor_sample(imu, imu_cfg) if imu else {'source': 'sensor'}

            draw(stdscr, data, imu_cfg, start_time, sample_count, actual_hz)
            sample_count    += 1
            hz_window_count += 1
        except Exception:
            pass  # transient error — next frame recovers

        # Update displayed Hz once per second
        now = time.monotonic()
        if now - hz_window_start >= 1.0:
            actual_hz       = hz_window_count / (now - hz_window_start)
            hz_window_count = 0
            hz_window_start = now

        elapsed   = time.monotonic() - loop_start
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    # Clean up I2C on exit
    if imu is not None:
        try:
            imu._i2c.deinit()
        except Exception:
            pass


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    try:
        imu_cfg = config.get_imu_settings()
        paths   = config.get_paths()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    if imu_cfg['sample_rate_hz'] < 1:
        print(f"ERROR: sample_rate_hz ({imu_cfg['sample_rate_hz']}) is below the "
              f"BNO085 minimum of 1 Hz. Set sample_rate_hz >= 1 in fishcam_config.yaml.")
        sys.exit(1)

    imu_dir = Path(__file__).parent / paths['imu_dir']

    if is_run_imu_active():
        print("run_imu.py is active — reading from live CSV (no I2C access).")
    else:
        print(f"Initialising BNO085 at I2C address 0x{imu_cfg['i2c_address']:02X}...")

    print("Starting monitor...")
    time.sleep(0.5)

    try:
        curses.wrapper(run_monitor, imu_cfg, imu_dir)
    except KeyboardInterrupt:
        pass

    print("Monitor stopped.")


if __name__ == '__main__':
    main()
