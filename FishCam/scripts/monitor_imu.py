#!/usr/bin/env python3
"""
FishCam IMU Monitor  (Testing Utility)

Real-time terminal display of BNO085 IMU data for testing and verification.
Designed to run over SSH — no screen or display hardware required.

Usage (from the scripts directory):
    python3 monitor_imu.py

Controls:
    q / Q / Esc  — quit

WARNING: Do NOT run while run_imu.py is running. Both scripts
access the same I2C device and will conflict.
"""

import curses
import math
import sys
import time

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


# ── IMU setup ──────────────────────────────────────────────────────────────────

def setup_imu(imu_cfg, max_attempts=5, retry_delay=2.0):
    """Initialise I2C bus and BNO085, enabling all configured reports.

    Retries several times with a delay to handle BNO085 cold-start timing —
    the sensor needs a moment after power-on before it accepts feature commands.
    """
    interval_us = int(1_000_000 / imu_cfg['sample_rate_hz'])  # µs per sample
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


# ── Display ────────────────────────────────────────────────────────────────────

def draw(stdscr, imu, imu_cfg, start_time, sample_count, actual_hz):
    """Read sensors and render one frame."""
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

    # ── Read sensors ──
    accel = imu.acceleration        if imu_cfg['accelerometer']      else None
    gyro  = imu.gyro                if imu_cfg['gyroscope']          else None
    mag   = imu.magnetic            if imu_cfg['magnetometer']       else None
    quat  = imu.quaternion          if imu_cfg['rotation_vector']    else None
    lin   = imu.linear_acceleration if imu_cfg['linear_acceleration'] else None
    grav  = imu.gravity             if imu_cfg['gravity']            else None

    # ── Euler angles from quaternion ──
    yaw, pitch, roll = None, None, None
    if quat is not None:
        qi, qj, qk, qr = quat
        if all(v is not None for v in (qi, qj, qk, qr)):
            yaw, pitch, roll = quat_to_euler(qi, qj, qk, qr)

    # ── Uptime ──
    elapsed = time.monotonic() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)

    # ── Render ──
    r = 0
    put(r, '═' * W); r += 1
    put(r, f'  FishCam IMU Monitor'
           f'  |  {imu_cfg["sample_rate_hz"]} Hz configured'
           f'  |  {actual_hz:.1f} Hz actual', bold=True); r += 1
    put(r, '═' * W); r += 1

    if imu_cfg['rotation_vector']:
        r += 1
        put(r, '  Orientation', bold=True); r += 1
        put(r, f'    Heading (mag N) : {fmt_angle(yaw):>8}°'); r += 1
        put(r, f'    Pitch           : {fmt_angle(pitch):>8}°'); r += 1
        put(r, f'    Roll            : {fmt_angle(roll):>8}°'); r += 1

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

def run_monitor(stdscr, imu, imu_cfg):
    """Curses main loop — reads IMU and refreshes display each sample interval."""
    curses.curs_set(0)   # hide cursor
    stdscr.nodelay(True) # non-blocking getch

    interval     = 1.0 / imu_cfg['sample_rate_hz']
    start_time   = time.monotonic()
    sample_count = 0

    # Rolling Hz measurement
    hz_window_start = time.monotonic()
    hz_window_count = 0
    actual_hz       = 0.0

    while True:
        loop_start = time.monotonic()

        # Quit on q / Q / Esc
        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break

        try:
            draw(stdscr, imu, imu_cfg, start_time, sample_count, actual_hz)
            sample_count    += 1
            hz_window_count += 1
        except Exception:
            pass  # ignore transient read errors — next frame will recover

        # Update displayed Hz once per second
        now = time.monotonic()
        if now - hz_window_start >= 1.0:
            actual_hz       = hz_window_count / (now - hz_window_start)
            hz_window_count = 0
            hz_window_start = now

        # Sleep for remainder of sample interval
        elapsed   = time.monotonic() - loop_start
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    try:
        imu_cfg = config.get_imu_settings()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    # BNO085 hardware limit: minimum sample rate is 1 Hz (maximum report interval
    # is 1,000,000 µs). Values below 1 Hz will cause enable_feature() to fail.
    if imu_cfg['sample_rate_hz'] < 1:
        print(f"ERROR: sample_rate_hz ({imu_cfg['sample_rate_hz']}) is below the "
              f"BNO085 minimum of 1 Hz. Set sample_rate_hz >= 1 in fishcam_config.yaml.")
        sys.exit(1)

    print(f"Initialising BNO085 at I2C address 0x{imu_cfg['i2c_address']:02X}...")
    try:
        imu = setup_imu(imu_cfg)
    except Exception as e:
        print(f"Failed to initialise IMU: {e}")
        print("Check wiring and that i2c_address in fishcam_config.yaml matches your hardware.")
        sys.exit(1)

    print("IMU ready. Starting monitor...")
    time.sleep(0.5)

    try:
        curses.wrapper(run_monitor, imu, imu_cfg)
    except KeyboardInterrupt:
        pass

    print("Monitor stopped.")


if __name__ == '__main__':
    main()
