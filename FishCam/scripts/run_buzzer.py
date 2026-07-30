#!/usr/bin/env python3
"""
FishCam Buzzer Controller

Plays acoustic beep sequences at configured times of day to allow
time-synchronization of multiple FishCam units in the field.

Each FishCam unit has a unique beep_count set in fishcam_config.yaml so that
recordings from different units can be identified by counting the beeps.

Runs as a background process started by fishcamStartup.sh.

Configuration (fishcam_config.yaml):
  buzzer.enabled                  : true/false
  buzzer.pin                      : GPIO pin number (BCM)
  buzzer.trigger_times            : list of "HH:MM" times (24-hour) to fire
  buzzer.beep_count               : beeps per sequence — set uniquely per fishcam unit
  buzzer.beep_duration_sec        : duration of each beep in seconds
  buzzer.beep_gap_sec             : silence between beeps within a sequence
  buzzer.number_sequences         : how many sequences to play per trigger
  buzzer.gap_between_sequences_sec: gap between repeated sequences in seconds
"""

import lgpio
import time
import logging
import sys
import re
import signal
from datetime import datetime, date, timedelta
from pathlib import Path

import config


def _setup_logging(log_path):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_path),
        ]
    )


def _parse_trigger_times(time_strings):
    """Parse list of 'HH:MM' strings into a sorted list of (hour, minute) tuples."""
    times = []
    for ts in time_strings:
        m = re.match(r'^(\d{1,2}):(\d{2})$', str(ts).strip())
        if not m:
            raise ValueError(f"Invalid trigger_time format: '{ts}'. Expected HH:MM.")
        h, mn = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mn <= 59):
            raise ValueError(f"Trigger time out of range: '{ts}'")
        times.append((h, mn))
    if not times:
        raise ValueError("trigger_times list is empty.")
    return sorted(times)


def _next_trigger(trigger_times):
    """Return the next trigger datetime (today or tomorrow if all times have passed)."""
    now = datetime.now()
    today = date.today()
    for h, mn in trigger_times:
        candidate = datetime(today.year, today.month, today.day, h, mn)
        if candidate > now:
            return candidate
    # All times have passed today — schedule for first time tomorrow
    tomorrow = today + timedelta(days=1)
    h, mn = trigger_times[0]
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, h, mn)


def _play_sequence(chip, pin, beep_dur, beep_gap, beep_count):
    """Play one beep sequence."""
    for _ in range(beep_count):
        lgpio.gpio_write(chip, pin, 1)
        time.sleep(beep_dur)
        lgpio.gpio_write(chip, pin, 0)
        time.sleep(beep_gap)


def main():
    fishcam_id = config.get_fishcam_id()
    buzzer_cfg = config.get_buzzer_settings()
    paths      = config.get_paths()

    log_dir = Path(__file__).parent / paths['log_dir']
    log_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(log_dir / f'buzzer_{fishcam_id}.log')

    logging.info('=' * 60)
    logging.info('FishCam Buzzer Controller')
    logging.info('=' * 60)

    if not buzzer_cfg.get('enabled', False):
        logging.info("Buzzer DISABLED in configuration. Exiting.")
        sys.exit(0)

    # Parse and validate trigger times
    try:
        trigger_times = _parse_trigger_times(buzzer_cfg.get('trigger_times', []))
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Read parameters — fail early with a clear message if a key is missing
    try:
        pin        = buzzer_cfg['pin']
        beep_count = buzzer_cfg['beep_count']
        beep_dur   = buzzer_cfg['beep_duration_sec']
        beep_gap   = buzzer_cfg['beep_gap_sec']
        num_seq    = buzzer_cfg['number_sequences']
        gap_btw    = buzzer_cfg['gap_between_sequences_sec']
    except KeyError as e:
        logging.error(f"Missing required buzzer configuration key: {e}. Check fishcam_config.yaml.")
        sys.exit(1)

    time_strs = [f'{h:02d}:{mn:02d}' for h, mn in trigger_times]
    logging.info(f"Trigger times          : {time_strs}")
    logging.info(f"Beeps per sequence     : {beep_count}")
    logging.info(f"Sequences per trigger  : {num_seq}")
    logging.info(f"Gap between sequences  : {gap_btw}s")
    logging.info(f"Beep duration          : {beep_dur}s")
    logging.info(f"Gap between beeps      : {beep_gap}s")

    # Graceful shutdown on SIGTERM / SIGINT
    _shutdown = {'requested': False}

    def _on_signal(signum, frame):
        logging.info(f"Signal {signum} received — shutting down buzzer controller")
        _shutdown['requested'] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    # Open GPIO — released in finally so buzzer is always left OFF
    chip = lgpio.gpiochip_open(0)
    try:
        lgpio.gpio_claim_output(chip, pin)
        lgpio.gpio_write(chip, pin, 0)
        logging.info(f"GPIO initialized: buzzer on pin {pin}")

        while not _shutdown['requested']:
            next_dt  = _next_trigger(trigger_times)
            wait_sec = (next_dt - datetime.now()).total_seconds()
            logging.info(f"Next trigger: {next_dt.strftime('%Y-%m-%d %H:%M')} "
                         f"(in {wait_sec / 60:.1f} min)")

            # Sleep in 5 s chunks so SIGTERM is caught promptly
            while not _shutdown['requested']:
                remaining = (next_dt - datetime.now()).total_seconds()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 5.0))

            if _shutdown['requested']:
                break

            logging.info(f"Trigger at {datetime.now().strftime('%H:%M:%S')} — "
                         f"playing {num_seq} sequence(s) of {beep_count} beep(s)")

            for seq in range(num_seq):
                if _shutdown['requested']:
                    break
                t0 = datetime.now()
                logging.info(f"Sequence {seq + 1}/{num_seq} at "
                             f"{t0.strftime('%H:%M:%S.%f')[:-3]}")
                _play_sequence(chip, pin, beep_dur, beep_gap, beep_count)
                if seq < num_seq - 1 and not _shutdown['requested']:
                    time.sleep(gap_btw)

    finally:
        lgpio.gpio_write(chip, pin, 0)   # ensure buzzer is OFF on exit
        lgpio.gpiochip_close(chip)
        logging.info("Buzzer controller stopped, GPIO released")


if __name__ == '__main__':
    main()
