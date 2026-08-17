#!/usr/bin/env python3
"""
FishCam IMU Acquisition Script

Continuously records data from the Adafruit BNO085 IMU via I2C and saves
it to a CSV file in the data directory. Runs as a background process
alongside video capture.

Hardware (I2C wiring):
- VIN → 3.3 V  (Pi Pin 1)
- GND → GND    (Pi Pin 6)
- SDA → GPIO 2 (Pi Pin 3)
- SCL → GPIO 3 (Pi Pin 5)

Output CSV columns (enabled reports only):
- timestamp_unix      : Unix timestamp (s, float)
- datetime            : ISO-8601 datetime string
- accel_{x,y,z}_ms2  : Accelerometer (m/s²)
- gyro_{x,y,z}_rads  : Gyroscope (rad/s)
- mag_{x,y,z}_uT     : Magnetometer (µT)
- quat_{i,j,k,real}  : Rotation vector (quaternion, dimensionless)
- calibration_status  : BNO085 orientation accuracy (0=unreliable … 3=high)
- heading_deg         : Yaw / heading referenced to magnetic north (0–360°)
- pitch_deg           : Pitch angle (degrees)
- roll_deg            : Roll angle (degrees)
- lin_accel_{x,y,z}_ms2 : Linear acceleration without gravity (m/s²)
- gravity_{x,y,z}_ms2   : Gravity vector (m/s²)
"""

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

import csv
import logging
import math
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import config


def quat_to_euler(i, j, k, real):
    """Convert quaternion to (heading, pitch, roll) in degrees.

    Heading is referenced to magnetic north, normalised to 0–360°.
    """
    heading = math.degrees(math.atan2(2*(real*k + i*j), 1 - 2*(j**2 + k**2)))
    pitch   = math.degrees(math.asin(max(-1.0, min(1.0, 2*(real*j - k*i)))))
    roll    = math.degrees(math.atan2(2*(real*i + j*k), 1 - 2*(i**2 + j**2)))
    return heading % 360, pitch, roll


class IMUAcquisition:
    """Acquires and records IMU data from the BNO085 via I2C."""

    # Number of samples between CSV flushes (limits data loss on power cut)
    FLUSH_INTERVAL = 10

    def __init__(self, sample_rate_hz, i2c_address,
                 enable_accelerometer, enable_gyroscope, enable_magnetometer,
                 enable_rotation_vector, enable_linear_acceleration, enable_gravity,
                 output_path):
        self.sample_rate_hz   = sample_rate_hz
        self.i2c_address      = i2c_address
        self.enable_accel     = enable_accelerometer
        self.enable_gyro      = enable_gyroscope
        self.enable_mag       = enable_magnetometer
        self.enable_rot       = enable_rotation_vector
        self.enable_lin_accel = enable_linear_acceleration
        self.enable_gravity   = enable_gravity
        self.output_path      = output_path

        self.shutdown_requested = False
        self._imu = None
        self._i2c = None
        self._sample_interval = 1.0 / sample_rate_hz

    # Errors that indicate an I2C bus or sensor crash requiring reinitialisation
    _CRASH_ERRORS = ('Unprocessable Batch bytes', '[Errno 5]', 'Input/output error')
    # Reinit after this many consecutive errors even if none are crash-type
    _MAX_CONSECUTIVE_ERRORS = 3

    # ── Setup ──────────────────────────────────────────────────────────────

    def _setup_imu(self, retry_delay=2.0, warn_every=10):
        """Initialise I2C bus and BNO085, then enable configured reports.

        Retries indefinitely with a delay to handle BNO085 cold-start timing or
        transient I2C errors. Logs a prominent warning every warn_every attempts
        so persistent hardware failures are visible in the log.
        """
        interval_us = int(1_000_000 / self.sample_rate_hz)  # µs per sample

        # Deinit any existing bus before creating a new one (prevents descriptor leak on retries)
        if self._i2c is not None:
            try:
                self._i2c.deinit()
            except Exception:
                pass
            self._i2c = None

        self._i2c = busio.I2C(board.SCL, board.SDA)

        attempt = 0
        while not self.shutdown_requested:
            attempt += 1
            try:
                self._imu = BNO08X_I2C(self._i2c, address=self.i2c_address)
                if self.enable_accel:
                    self._imu.enable_feature(BNO_REPORT_ACCELEROMETER,
                                             report_interval=interval_us)
                if self.enable_gyro:
                    self._imu.enable_feature(BNO_REPORT_GYROSCOPE,
                                             report_interval=interval_us)
                if self.enable_mag:
                    self._imu.enable_feature(BNO_REPORT_MAGNETOMETER,
                                             report_interval=interval_us)
                if self.enable_rot:
                    self._imu.enable_feature(BNO_REPORT_ROTATION_VECTOR,
                                             report_interval=interval_us)
                if self.enable_lin_accel:
                    self._imu.enable_feature(BNO_REPORT_LINEAR_ACCELERATION,
                                             report_interval=interval_us)
                if self.enable_gravity:
                    self._imu.enable_feature(BNO_REPORT_GRAVITY,
                                             report_interval=interval_us)
                logging.info(f"IMU initialised at I2C address 0x{self.i2c_address:02X}, "
                             f"sample rate {self.sample_rate_hz} Hz "
                             f"(attempt {attempt})")
                return
            except Exception as e:
                if attempt % warn_every == 0:
                    logging.error(f"IMU still failing after {attempt} attempts — "
                                  f"check wiring and I2C address. Last error: {e}")
                else:
                    logging.warning(f"IMU init attempt {attempt} failed: {e} "
                                    f"— retrying in {retry_delay}s...")
                time.sleep(retry_delay)

    def _is_crash_error(self, e):
        """Return True if the error signals an I2C bus or sensor crash."""
        err_str = str(e)
        return any(marker in err_str for marker in self._CRASH_ERRORS)

    def _reinit_imu(self, recovery_delay=5.0):
        """Tear down the I2C bus and reinitialise the IMU after a crash.

        A hard deinit of the busio.I2C object releases the kernel I2C driver
        lock, allowing the bus to recover from a stuck-low or corrupted state.
        """
        logging.warning("IMU crash detected — tearing down I2C bus for recovery...")
        try:
            if self._i2c is not None:
                self._i2c.deinit()
                self._i2c = None
        except Exception as e:
            logging.warning(f"Error during I2C deinit (ignoring): {e}")

        logging.info(f"Waiting {recovery_delay}s for sensor to power-cycle and settle...")
        time.sleep(recovery_delay)

        self._setup_imu()
        logging.info("IMU recovery complete — resuming acquisition")

    # ── CSV helpers ────────────────────────────────────────────────────────

    def _build_header(self):
        """Return ordered list of CSV column names for enabled reports."""
        cols = ['timestamp_unix', 'datetime']
        if self.enable_accel:
            cols += ['accel_x_ms2', 'accel_y_ms2', 'accel_z_ms2']
        if self.enable_gyro:
            cols += ['gyro_x_rads', 'gyro_y_rads', 'gyro_z_rads']
        if self.enable_mag:
            cols += ['mag_x_uT', 'mag_y_uT', 'mag_z_uT']
        if self.enable_rot:
            cols += ['quat_i', 'quat_j', 'quat_k', 'quat_real',
                     'calibration_status',
                     'heading_deg', 'pitch_deg', 'roll_deg']
        if self.enable_lin_accel:
            cols += ['lin_accel_x_ms2', 'lin_accel_y_ms2', 'lin_accel_z_ms2']
        if self.enable_gravity:
            cols += ['gravity_x_ms2', 'gravity_y_ms2', 'gravity_z_ms2']
        return cols

    # ── Sample reading ─────────────────────────────────────────────────────

    @staticmethod
    def _fmt(value):
        """Format a float to 6 decimal places, or empty string if None."""
        return f'{value:.6f}' if value is not None else ''

    def _read_sample(self):
        """Read one sample from all enabled reports. Returns a dict."""
        now = time.time()
        row = {
            'timestamp_unix': f'{now:.6f}',
            'datetime': datetime.now().astimezone().strftime('%Y%m%dT%H%M%S.%f%z'),
        }

        if self.enable_accel:
            val = self._imu.acceleration  # (x, y, z) m/s² or None
            x, y, z = val if val is not None else (None, None, None)
            row['accel_x_ms2'] = self._fmt(x)
            row['accel_y_ms2'] = self._fmt(y)
            row['accel_z_ms2'] = self._fmt(z)

        if self.enable_gyro:
            val = self._imu.gyro          # (x, y, z) rad/s or None
            x, y, z = val if val is not None else (None, None, None)
            row['gyro_x_rads'] = self._fmt(x)
            row['gyro_y_rads'] = self._fmt(y)
            row['gyro_z_rads'] = self._fmt(z)

        if self.enable_mag:
            val = self._imu.magnetic      # (x, y, z) µT or None
            x, y, z = val if val is not None else (None, None, None)
            row['mag_x_uT'] = self._fmt(x)
            row['mag_y_uT'] = self._fmt(y)
            row['mag_z_uT'] = self._fmt(z)

        if self.enable_rot:
            val = self._imu.quaternion    # (i, j, k, real) or None
            i, j, k, r = val if val is not None else (None, None, None, None)
            row['quat_i']    = self._fmt(i)
            row['quat_j']    = self._fmt(j)
            row['quat_k']    = self._fmt(k)
            row['quat_real'] = self._fmt(r)
            cal = self._imu.calibration_status  # 0–3 or None
            row['calibration_status'] = str(cal) if cal is not None else ''
            if all(v is not None for v in (i, j, k, r)):
                heading, pitch, roll = quat_to_euler(i, j, k, r)
                row['heading_deg'] = self._fmt(heading)
                row['pitch_deg']   = self._fmt(pitch)
                row['roll_deg']    = self._fmt(roll)
            else:
                row['heading_deg'] = ''
                row['pitch_deg']   = ''
                row['roll_deg']    = ''

        if self.enable_lin_accel:
            val = self._imu.linear_acceleration  # (x, y, z) m/s² or None
            x, y, z = val if val is not None else (None, None, None)
            row['lin_accel_x_ms2'] = self._fmt(x)
            row['lin_accel_y_ms2'] = self._fmt(y)
            row['lin_accel_z_ms2'] = self._fmt(z)

        if self.enable_gravity:
            val = self._imu.gravity       # (x, y, z) m/s² or None
            x, y, z = val if val is not None else (None, None, None)
            row['gravity_x_ms2'] = self._fmt(x)
            row['gravity_y_ms2'] = self._fmt(y)
            row['gravity_z_ms2'] = self._fmt(z)

        return row

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self):
        """Set up the IMU then loop, writing one CSV row per sample."""
        logging.info("Setting up IMU...")
        self._setup_imu()

        header = self._build_header()
        logging.info(f"Opening IMU data file: {self.output_path}")

        with open(self.output_path, 'w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=header)
            writer.writeheader()
            csv_file.flush()

            logging.info("IMU acquisition started")
            sample_count = 0
            consecutive_errors = 0

            while not self.shutdown_requested:
                loop_start = time.monotonic()

                try:
                    row = self._read_sample()
                    writer.writerow(row)
                    sample_count += 1
                    consecutive_errors = 0  # reset on successful read

                    # Periodic flush to limit data loss on power cut
                    if sample_count % self.FLUSH_INTERVAL == 0:
                        csv_file.flush()

                except Exception as e:
                    consecutive_errors += 1
                    is_crash = self._is_crash_error(e)
                    logging.error(f"Failed to read IMU sample "
                                  f"(consecutive: {consecutive_errors}): {e}")

                    if is_crash or consecutive_errors >= self._MAX_CONSECUTIVE_ERRORS:
                        consecutive_errors = 0
                        self._reinit_imu()

                # Sleep for the remainder of the sample interval
                elapsed = time.monotonic() - loop_start
                remaining = self._sample_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)

        logging.info("IMU acquisition stopped")

    # ── Signal handling ────────────────────────────────────────────────────

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logging.info(f"Received signal {signum}, shutting down...")
        self.shutdown_requested = True


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    # Setup logging
    log_dir = Path(__file__).parent / config.get_paths()['log_dir']
    log_dir.mkdir(parents=True, exist_ok=True)
    fishcam_id = config.get_fishcam_id()
    log_file = log_dir / f'imu_{fishcam_id}.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_file),
        ]
    )

    logging.info('=' * 60)
    logging.info('FishCam IMU Acquisition')
    logging.info('=' * 60)

    # Load configuration
    try:
        imu_cfg = config.get_imu_settings()
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    if not imu_cfg['enabled']:
        logging.info("IMU acquisition is DISABLED in configuration")
        logging.info("To enable: set 'imu.enabled: true' in fishcam_config.yaml")
        sys.exit(0)

    # BNO085 hardware limit: minimum sample rate is 1 Hz (maximum report interval
    # is 1,000,000 µs). Values below 1 Hz will cause enable_feature() to fail.
    if imu_cfg['sample_rate_hz'] < 1:
        logging.error(f"sample_rate_hz ({imu_cfg['sample_rate_hz']}) is below the "
                      f"BNO085 minimum of 1 Hz. Set sample_rate_hz >= 1 in fishcam_config.yaml.")
        sys.exit(1)

    # Build output file path: ../data/imu/{timestamp}_{fishcam_id}_imu.csv
    paths    = config.get_paths()
    data_dir = Path(__file__).parent / paths['imu_dir']
    data_dir.mkdir(parents=True, exist_ok=True)

    _MAX_RESTARTS    = 5
    _RESTART_DELAY_S = 15
    consecutive_restarts = 0

    while True:
        # New timestamp and CSV file on each start/restart so sessions don't overlap
        timestamp = datetime.now().strftime('%Y%m%dT%H%M%S.%fZ')
        csv_path  = data_dir / f'{timestamp}_{fishcam_id}_imu.csv'

        logging.info("IMU acquisition ENABLED")
        logging.info(f"I2C address  : 0x{imu_cfg['i2c_address']:02X}")
        logging.info(f"Sample rate  : {imu_cfg['sample_rate_hz']} Hz")
        logging.info(f"Output file  : {csv_path}")
        logging.info("Enabled reports:")
        for report in ('accelerometer', 'gyroscope', 'magnetometer',
                       'rotation_vector', 'linear_acceleration', 'gravity'):
            logging.info(f"  {report}: {imu_cfg[report]}")

        acquisition = IMUAcquisition(
            sample_rate_hz             = imu_cfg['sample_rate_hz'],
            i2c_address                = imu_cfg['i2c_address'],
            enable_accelerometer       = imu_cfg['accelerometer'],
            enable_gyroscope           = imu_cfg['gyroscope'],
            enable_magnetometer        = imu_cfg['magnetometer'],
            enable_rotation_vector     = imu_cfg['rotation_vector'],
            enable_linear_acceleration = imu_cfg['linear_acceleration'],
            enable_gravity             = imu_cfg['gravity'],
            output_path                = csv_path,
        )

        signal.signal(signal.SIGTERM, acquisition.signal_handler)
        signal.signal(signal.SIGINT,  acquisition.signal_handler)
        logging.info("Signal handlers registered")

        try:
            acquisition.run()
        except Exception as e:
            if acquisition.shutdown_requested:
                break
            consecutive_restarts += 1
            logging.error(
                f"IMU acquisition error (restart {consecutive_restarts}/{_MAX_RESTARTS}): {e}"
            )
            if consecutive_restarts >= _MAX_RESTARTS:
                logging.error("Too many consecutive IMU restarts — stopping IMU acquisition.")
                sys.exit(1)
            logging.info(f"Restarting IMU acquisition in {_RESTART_DELAY_S}s...")
            time.sleep(_RESTART_DELAY_S)
            continue

        break  # clean shutdown (shutdown_requested)


if __name__ == '__main__':
    main()
