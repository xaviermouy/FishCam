#!/usr/bin/env python3
"""
FishCam IMU Calibration

Interactive calibration guide for the BNO085 IMU.
Tracks live magnetometer axis coverage and orientation diversity to guide
the calibration procedure.  Run before each deployment to confirm the IMU
is properly calibrated.

Usage:
    python3 calibrate_imu.py           # interactive calibration guide
    python3 calibrate_imu.py --check   # print current status and exit

Controls (interactive mode):
    q / Q / Esc  — quit
"""

import argparse
import curses
import subprocess
import sys
import time
from pathlib import Path

import config
import board
import busio
from adafruit_bno08x import (
    BNO_REPORT_GRAVITY,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_ROTATION_VECTOR,
)
from adafruit_bno08x.i2c import BNO08X_I2C


SCRIPT_DIR = Path(__file__).parent

_CAL_LABELS = {0: 'unreliable', 1: 'low', 2: 'medium', 3: 'high'}

# Span (µT) considered full-bar coverage — Earth's field is ~25–65 µT total,
# so a well-rotated unit should achieve ~2× that on each axis.
_MAG_TARGET_UT = 120.0

# Octant definitions: 8 combinations of gravity-vector signs (+X/−X, +Y/−Y, +Z/−Z)
_OCTANT_LABELS = [
    '-X-Y-Z', '-X-Y+Z', '-X+Y-Z', '-X+Y+Z',
    '+X-Y-Z', '+X-Y+Z', '+X+Y-Z', '+X+Y+Z',
]


# ── Process helpers ────────────────────────────────────────────────────────────

def is_run_imu_active():
    r = subprocess.run(['pgrep', '-f', 'run_imu.py'], capture_output=True)
    return r.returncode == 0


def stop_run_imu(timeout=5.0):
    """Send SIGTERM to run_imu.py and wait for it to exit. Returns True on success."""
    subprocess.run(['pkill', '-TERM', '-f', 'run_imu.py'], capture_output=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_run_imu_active():
            return True
        time.sleep(0.5)
    return False


# ── CSV reading (for --check mode without I2C access) ─────────────────────────

def _read_cal_from_csv(imu_dir):
    """Return (calibration_status, age_s) from the latest IMU CSV, or (None, None)."""
    candidates = list(Path(imu_dir).glob('*.csv'))
    if not candidates:
        return None, None
    csv_path = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        with open(csv_path, 'rb') as f:
            header = f.readline().decode().strip()
            if not header:
                return None, None
            try:
                f.seek(-2, 2)
            except OSError:
                return None, None
            while f.read(1) != b'\n':
                try:
                    f.seek(-2, 1)
                except OSError:
                    return None, None
            last_line = f.readline().decode().strip()
        row = dict(zip(header.split(','), last_line.split(',')))
        cal_raw = row.get('calibration_status', '').strip()
        cal = int(cal_raw) if cal_raw.isdigit() else None
        age_s = int(time.time() - csv_path.stat().st_mtime)
        return cal, age_s
    except Exception:
        return None, None


# ── IMU setup ──────────────────────────────────────────────────────────────────

def setup_imu(imu_cfg):
    """Initialise I2C and BNO085 with mag, rotation vector, and gravity reports."""
    rate_hz    = max(imu_cfg.get('sample_rate_hz', 10), 10)
    interval_us = int(1_000_000 / rate_hz)
    i2c = busio.I2C(board.SCL, board.SDA)
    imu = BNO08X_I2C(i2c, address=imu_cfg['i2c_address'])
    imu.enable_feature(BNO_REPORT_MAGNETOMETER,    report_interval=interval_us)
    imu.enable_feature(BNO_REPORT_ROTATION_VECTOR, report_interval=interval_us)
    imu.enable_feature(BNO_REPORT_GRAVITY,         report_interval=interval_us)
    return imu, i2c


# ── Octant helper ──────────────────────────────────────────────────────────────

def _grav_octant(grav):
    """Return octant index 0–7 from gravity-vector signs, or None if unavailable."""
    if grav is None:
        return None
    gx, gy, gz = grav
    if any(v is None for v in (gx, gy, gz)):
        return None
    return (4 if gx >= 0 else 0) | (2 if gy >= 0 else 0) | (1 if gz >= 0 else 0)


# ── Display helpers ────────────────────────────────────────────────────────────

def _bar(fraction, width=14):
    n = min(int(fraction * width), width)
    return '█' * n + '░' * (width - n)


# ── Check mode ─────────────────────────────────────────────────────────────────

def check_mode(imu_cfg, paths):
    """Print current calibration status and return."""
    imu_dir = SCRIPT_DIR / paths['imu_dir']

    # Prefer CSV (no I2C conflict if run_imu.py is running)
    cal, age_s = _read_cal_from_csv(imu_dir)
    source = 'last CSV'

    if cal is None and not is_run_imu_active():
        # No CSV and no recording process — read sensor directly
        try:
            imu, i2c = setup_imu(imu_cfg)
            time.sleep(0.5)
            cal    = imu.calibration_status
            age_s  = 0
            source = 'sensor'
            i2c.deinit()
        except Exception as e:
            print(f'  Could not read IMU sensor: {e}')

    if cal is None:
        print('  Calibration status : unknown')
        print('  (no CSV data and run_imu.py is not running)')
    else:
        label   = _CAL_LABELS.get(cal, str(cal))
        age_str = f'{age_s}s ago' if age_s is not None else 'unknown age'
        print(f'  Calibration accuracy : {cal} – {label}  (from {source}, {age_str})')


# ── Full calibration mode ──────────────────────────────────────────────────────

def _draw(stdscr, cal, mag_min, mag_max, visited_octants, fishcam_id, elapsed_s):
    stdscr.erase()
    max_rows, max_cols = stdscr.getmaxyx()
    W = max_cols

    def put(row, text, bold=False):
        if row >= max_rows - 1:
            return
        try:
            stdscr.addstr(row, 0, text[:W], curses.A_BOLD if bold else curses.A_NORMAL)
        except curses.error:
            pass

    h = int(elapsed_s // 3600)
    m = int((elapsed_s % 3600) // 60)
    s = int(elapsed_s % 60)

    cal_label = f'{cal} – {_CAL_LABELS.get(cal, "?")}' if cal is not None else '---'

    r = 0
    put(r, '═' * W); r += 1
    put(r, f'  FishCam IMU Calibration  |  {fishcam_id}', bold=True); r += 1
    put(r, '═' * W); r += 1

    r += 1
    put(r, f'  Overall accuracy  :  {cal_label}     (target: 3 – high)', bold=True); r += 1

    # ── Magnetometer coverage ─────────────────────────────────────────────────
    r += 1
    put(r, '  Magnetometer coverage  (slow figure-8 rotations in all directions)', bold=True); r += 1
    put(r, f'  {"":16}    {"min":>9}  {"max":>9}  {"span":>9}'); r += 1

    spans = []
    for i, axis in enumerate('XYZ'):
        lo = mag_min[i]
        hi = mag_max[i]
        if lo is not None and hi is not None:
            span = hi - lo
            spans.append(span)
            frac    = min(span / _MAG_TARGET_UT, 1.0)
            bar_str = _bar(frac)
            put(r, f'  {axis}  {bar_str}  {lo:>+8.1f}µT {hi:>+8.1f}µT {span:>7.1f}µT'); r += 1
        else:
            spans.append(0.0)
            put(r, f'  {axis}  {"░" * 14}       ---        ---       ---'); r += 1

    if any(sp > 0 for sp in spans):
        min_idx  = spans.index(min(spans))
        min_axis = 'XYZ'[min_idx]
        r += 1
        put(r, f'  → Axis {min_axis} has the smallest range — rotate more around that axis'); r += 1

    # ── Orientation coverage ──────────────────────────────────────────────────
    r += 1
    put(r, '  Orientation coverage  (tilt unit into 8 different positions)', bold=True); r += 1
    for row_start in (0, 4):
        line = '  '
        for idx in range(row_start, row_start + 4):
            mark = '✓' if idx in visited_octants else '✗'
            line += f'{mark} {_OCTANT_LABELS[idx]}   '
        put(r, line); r += 1
    put(r, f'  Visited: {len(visited_octants)} / 8'); r += 1

    # ── Protocol reminder ─────────────────────────────────────────────────────
    r += 1
    put(r, '  Protocol', bold=True); r += 1
    put(r, '    1. Hold completely still for ~15s        (gyro)'); r += 1
    put(r, '    2. Slow figure-8 motions through all axes (magnetometer)'); r += 1
    put(r, '    3. Tilt to 6+ stable positions            (accelerometer)'); r += 1
    put(r, '    Keep unit away from electronics and metal surfaces.'); r += 1

    r += 1
    put(r, '─' * W); r += 1
    done = '  ★ Calibration complete! ' if cal == 3 else ''
    put(r, f'  Elapsed: {h:02d}:{m:02d}:{s:02d}  |  Accuracy: {cal_label}  |  {done}Press q to exit'); r += 1
    put(r, '═' * W)

    stdscr.refresh()


def run_calibration(stdscr, imu, fishcam_id):
    curses.curs_set(0)
    stdscr.nodelay(True)

    mag_min        = [None, None, None]
    mag_max        = [None, None, None]
    visited_octants = set()
    start_time     = time.monotonic()

    while True:
        loop_start = time.monotonic()

        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break

        try:
            mag  = imu.magnetic
            grav = imu.gravity
            cal  = imu.calibration_status
        except Exception:
            mag = grav = cal = None

        # Accumulate mag range
        if mag is not None:
            for i, v in enumerate(mag):
                if v is not None:
                    mag_min[i] = v if mag_min[i] is None else min(mag_min[i], v)
                    mag_max[i] = v if mag_max[i] is None else max(mag_max[i], v)

        # Record orientation octant
        oct_idx = _grav_octant(grav)
        if oct_idx is not None:
            visited_octants.add(oct_idx)

        _draw(stdscr, cal, mag_min, mag_max, visited_octants,
              fishcam_id, time.monotonic() - start_time)

        remaining = 0.1 - (time.monotonic() - loop_start)
        if remaining > 0:
            time.sleep(remaining)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='BNO085 IMU calibration guide')
    parser.add_argument('--check', action='store_true',
                        help='Print current calibration status and exit')
    args = parser.parse_args()

    try:
        imu_cfg    = config.get_imu_settings()
        paths      = config.get_paths()
        fishcam_id = config.get_fishcam_id()
    except Exception as e:
        print(f'  Failed to load configuration: {e}')
        sys.exit(1)

    if args.check:
        check_mode(imu_cfg, paths)
        return

    # ── Full calibration mode ─────────────────────────────────────────────────

    if is_run_imu_active():
        print()
        print('  WARNING: run_imu.py is currently running (I2C bus conflict).')
        print()
        try:
            answer = input('  Stop run_imu.py and proceed with calibration? [y/n]  ').strip().lower()
        except (KeyboardInterrupt, EOFError):
            print('\n  Aborted.')
            sys.exit(0)
        if answer != 'y':
            print('  Aborted.')
            sys.exit(0)
        print('  Stopping run_imu.py...')
        if not stop_run_imu():
            print('  ERROR: Could not stop run_imu.py within 5s. Aborted.')
            sys.exit(1)
        print('  run_imu.py stopped.')
        print()

    print('  Initialising IMU...')
    try:
        imu, i2c = setup_imu(imu_cfg)
    except Exception as e:
        print(f'  Failed to initialise IMU: {e}')
        sys.exit(1)

    print('  Starting calibration guide...')
    time.sleep(0.5)

    try:
        curses.wrapper(run_calibration, imu, fishcam_id)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            i2c.deinit()
        except Exception:
            pass

    print('  Calibration session ended.')


if __name__ == '__main__':
    main()
