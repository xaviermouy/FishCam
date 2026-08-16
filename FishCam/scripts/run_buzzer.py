#!/usr/bin/env python3
"""
FishCam Buzzer Controller

Plays acoustic sequences at configured times of day to allow TDOA-based
localization and time-synchronization of multiple FishCam units.

Two sequence modes are supported (set via buzzer.sequence_mode in config):

  msequence (recommended):
      Each unit plays a unique m-sequence (maximal-length binary sequence)
      derived automatically from the FishCam unit number in the hostname
      (e.g. 'fishcam02' → unit 2). No per-unit config edit needed.
      Provides excellent autocorrelation properties for TDOA cross-correlation.

  beep (legacy):
      Each unit plays a fixed number of on/off beeps. Requires
      buzzer.beep_count to be set uniquely per unit in fishcam_config.yaml.

Configuration (fishcam_config.yaml):
  buzzer.enabled                  : true/false
  buzzer.pin                      : GPIO pin number (BCM)
  buzzer.trigger_times            : list of "HH:MM" times (24-hour, local time)
  buzzer.sequence_mode            : 'msequence' or 'beep'
  buzzer.number_sequences         : how many sequences to play per trigger
  buzzer.gap_between_sequences_sec: gap between repeated sequences in seconds
  buzzer.missed_trigger_grace_sec : seconds after scheduled time to still fire

  For msequence mode:
  buzzer.msequence_n              : LFSR length (5 → 31 chips, 6 → 63 chips)
  buzzer.chip_duration_sec        : duration of each chip in seconds

  For beep (legacy) mode:
  buzzer.beep_count               : beeps per sequence — set uniquely per unit
  buzzer.beep_duration_sec        : duration of each beep in seconds
  buzzer.beep_gap_sec             : silence between beeps within a sequence
"""

import lgpio
import time
import logging
import sys
import re
import signal
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import config


# ---------------------------------------------------------------------------
# M-sequence support
# ---------------------------------------------------------------------------

# Feedback tap positions for Fibonacci LFSR over GF(2).
#
# Each entry lists ALL positions to XOR (1-indexed, where tap k → state[k-1]).
# The feedback bit = XOR of state[tap-1] for every tap in the list.
# This directly encodes the characteristic polynomial recurrence:
#   a_{t+n} = XOR of a_{t+tap-1} for each tap
#
# Taps are derived from primitive polynomials, which guarantee maximal-length
# sequences (period = 2^n - 1). All entries are validated at startup.
#
#   n=5  → sequence length 31 chips  (covers units 1–6)
#   n=6  → sequence length 63 chips  (covers units 1–6)
#
_MSEQ_TAPS = {
    5: {
        1: [3, 1],        # x^5 + x^2 + 1
        2: [4, 1],        # x^5 + x^3 + 1
        3: [4, 3, 2, 1],  # x^5 + x^3 + x^2 + x + 1
        4: [5, 3, 2, 1],  # x^5 + x^4 + x^2 + x + 1
        5: [5, 4, 2, 1],  # x^5 + x^4 + x^3 + x + 1
        6: [5, 4, 3, 1],  # x^5 + x^4 + x^3 + x^2 + 1
    },
    6: {
        1: [6, 1],        # x^6 + x^5 + 1
        2: [2, 1],        # x^6 + x + 1
        3: [6, 3, 2, 1],  # x^6 + x^5 + x^2 + x + 1
        4: [6, 4, 3, 1],  # x^6 + x^5 + x^3 + x^2 + 1
        5: [6, 5, 3, 1],  # x^6 + x^5 + x^4 + x^2 + 1
        6: [6, 5, 2, 1],  # x^6 + x^5 + x^4 + x + 1
    },
}


def _generate_msequence(n, taps):
    """Generate a binary m-sequence of length 2^n - 1 using a Fibonacci LFSR.

    The LFSR is initialised to all-ones. At each step the output bit is
    state[0], the feedback is XOR of state[tap-1] for every tap in the list,
    and the register shifts left with the feedback appended.

    Args:
        n:    Shift register length (degree of primitive polynomial).
        taps: ALL feedback tap positions (1-indexed). Must encode a primitive
              polynomial. Example: x^6 + x + 1  →  n=6, taps=[2, 1]
              (recurrence a_{t+6} = a_{t+1} + a_t)

    Returns:
        List of int (0 or 1) of length 2^n - 1.

    Raises:
        ValueError: If the LFSR does not achieve maximal length (bad taps).
    """
    state        = [1] * n
    initial      = state[:]
    expected_len = (1 << n) - 1
    seq          = []

    for step in range(expected_len + 1):   # +1 to detect premature cycling
        out      = state[0]
        feedback = 0
        for tap in taps:
            feedback ^= state[tap - 1]
        state = state[1:] + [feedback]

        if step < expected_len:
            seq.append(out)

        if state == initial:
            if step + 1 != expected_len:
                raise ValueError(
                    f"LFSR cycle after {step + 1} steps (expected {expected_len}). "
                    f"Taps {taps} are not a primitive polynomial for n={n}. "
                    f"Check the _MSEQ_TAPS table."
                )
            break

    return seq


def _validate_msequence_taps(n):
    """Validate every tap entry for n by generating each sequence at startup.

    Raises ValueError if n is unsupported or any tap set is not primitive.
    This ensures bad polynomials are caught immediately on every unit.
    """
    if n not in _MSEQ_TAPS:
        raise ValueError(
            f"No m-sequence tap table defined for n={n}. "
            f"Supported values: {sorted(_MSEQ_TAPS.keys())}"
        )
    for unit_num, taps in _MSEQ_TAPS[n].items():
        seq = _generate_msequence(n, taps)   # raises if not maximal-length
        expected = (1 << n) - 1
        if len(seq) != expected:
            raise ValueError(
                f"Unit {unit_num} sequence length {len(seq)} != {expected} for n={n}, taps={taps}"
            )


def _get_unit_number(fishcam_id):
    """Extract the integer unit number from the fishcam hostname.

    'fishcam01' → 1,   'fishcam06' → 6.

    Raises:
        ValueError: If no trailing number is found.
    """
    m = re.search(r'(\d+)$', fishcam_id)
    if not m:
        raise ValueError(
            f"Cannot extract unit number from fishcam ID '{fishcam_id}'. "
            f"Hostname must end with digits (e.g. 'fishcam01')."
        )
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Sequence playback
# ---------------------------------------------------------------------------

def _play_msequence(chip, pin, pattern, chip_dur):
    """Play one m-sequence: drive the buzzer pin per the binary pattern.

    Each chip (0 or 1) is held for chip_dur seconds. The pin is driven LOW
    after the last chip to ensure the buzzer is always left OFF.
    """
    for bit in pattern:
        lgpio.gpio_write(chip, pin, bit)
        time.sleep(chip_dur)
    lgpio.gpio_write(chip, pin, 0)


def _play_beep_sequence(chip, pin, beep_dur, beep_gap, beep_count):
    """Play one legacy beep sequence (beep mode)."""
    for _ in range(beep_count):
        lgpio.gpio_write(chip, pin, 1)
        time.sleep(beep_dur)
        lgpio.gpio_write(chip, pin, 0)
        time.sleep(beep_gap)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(log_path):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_path),
        ]
    )


# ---------------------------------------------------------------------------
# Trigger scheduling helpers
# ---------------------------------------------------------------------------

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


def _next_trigger(trigger_times, local_tz, grace_sec, fired_today):
    """Return (next_utc, (sched_h, sched_mn)) for the next trigger to fire.

    Trigger times are specified in local_tz but compared against UTC (Pi clock).
    Priority order:
      1. Most recently missed trigger within grace_sec, not already fired.
      2. Next future trigger not already fired today.
      3. First trigger tomorrow (fired_today resets at midnight local time).
    """
    now_utc     = datetime.now()
    today_local = datetime.now(tz=local_tz).date()

    if grace_sec > 0:
        for h, mn in reversed(trigger_times):
            if (h, mn) in fired_today:
                continue
            local_dt = datetime(today_local.year, today_local.month, today_local.day,
                                h, mn, tzinfo=local_tz)
            utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
            seconds_past = (now_utc - utc_dt).total_seconds()
            if 0 < seconds_past <= grace_sec:
                return utc_dt, (h, mn)

    for h, mn in trigger_times:
        if (h, mn) in fired_today:
            continue
        local_dt = datetime(today_local.year, today_local.month, today_local.day,
                            h, mn, tzinfo=local_tz)
        utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        if utc_dt > now_utc:
            return utc_dt, (h, mn)

    tomorrow_local = today_local + timedelta(days=1)
    h, mn = trigger_times[0]
    local_dt = datetime(tomorrow_local.year, tomorrow_local.month, tomorrow_local.day,
                        h, mn, tzinfo=local_tz)
    utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_dt, (h, mn)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    # Common parameters
    try:
        pin       = buzzer_cfg['pin']
        num_seq   = buzzer_cfg['number_sequences']
        gap_btw   = buzzer_cfg['gap_between_sequences_sec']
        grace_sec = buzzer_cfg['missed_trigger_grace_sec']
        tz_name   = buzzer_cfg['deployment_timezone']
        seq_mode  = buzzer_cfg.get('sequence_mode', 'beep')
    except KeyError as e:
        logging.error(f"Missing required configuration key: {e}. Check fishcam_config.yaml.")
        sys.exit(1)

    # Mode-specific setup and validation
    if seq_mode == 'msequence':
        try:
            n        = buzzer_cfg['msequence_n']
            chip_dur = buzzer_cfg['chip_duration_sec']
            unit_num = _get_unit_number(fishcam_id)
        except (KeyError, ValueError) as e:
            logging.error(f"M-sequence configuration error: {e}")
            sys.exit(1)

        logging.info("Validating m-sequence tap table ...")
        try:
            _validate_msequence_taps(n)
        except (ValueError, AssertionError) as e:
            logging.error(f"M-sequence tap validation FAILED: {e}")
            sys.exit(1)
        logging.info("M-sequence tap table OK")

        if unit_num not in _MSEQ_TAPS[n]:
            max_unit = max(_MSEQ_TAPS[n].keys())
            logging.error(
                f"Unit number {unit_num} (hostname '{fishcam_id}') has no m-sequence "
                f"assignment for n={n}. Supported unit numbers: 1–{max_unit}."
            )
            sys.exit(1)

        taps         = _MSEQ_TAPS[n][unit_num]
        pattern      = _generate_msequence(n, taps)
        seq_duration = len(pattern) * chip_dur

        logging.info(f"Sequence mode          : msequence")
        logging.info(f"M-sequence n           : {n}")
        logging.info(f"Unit number            : {unit_num}")
        logging.info(f"Polynomial taps        : {taps}")
        logging.info(f"Chip duration          : {chip_dur}s")
        logging.info(f"Sequence length        : {len(pattern)} chips ({seq_duration:.1f}s)")
        logging.info(f"Sequence pattern       : {','.join(str(b) for b in pattern)}")
        seq_desc = f"m-sequence (n={n}, {len(pattern)} chips, {seq_duration:.1f}s)"

    else:  # 'beep' legacy mode
        try:
            beep_count = buzzer_cfg['beep_count']
            beep_dur   = buzzer_cfg['beep_duration_sec']
            beep_gap   = buzzer_cfg['beep_gap_sec']
        except KeyError as e:
            logging.error(f"Missing beep configuration key: {e}. Check fishcam_config.yaml.")
            sys.exit(1)
        logging.info(f"Sequence mode          : beep")
        logging.info(f"Beeps per sequence     : {beep_count}")
        logging.info(f"Beep duration          : {beep_dur}s")
        logging.info(f"Gap between beeps      : {beep_gap}s")
        seq_desc = f"{beep_count} beep(s)"

    try:
        local_tz = ZoneInfo(tz_name)
    except Exception as e:
        logging.error(f"Invalid timezone '{tz_name}': {e}. Check 'deployment_timezone' in fishcam_config.yaml.")
        sys.exit(1)

    time_strs = [f'{h:02d}:{mn:02d}' for h, mn in trigger_times]
    logging.info(f"Timezone               : {tz_name} (trigger times are local; logs are UTC)")
    logging.info(f"Trigger times (local)  : {time_strs}")
    logging.info(f"Missed trigger grace   : {grace_sec}s")
    logging.info(f"Sequences per trigger  : {num_seq}")
    logging.info(f"Gap between sequences  : {gap_btw}s")

    # Graceful shutdown on SIGTERM / SIGINT
    _shutdown = {'requested': False}

    def _on_signal(signum, frame):
        logging.info(f"Signal {signum} received — shutting down buzzer controller")
        _shutdown['requested'] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    _MAX_LOOP_FAILURES = 5
    _LOOP_RETRY_DELAY  = 15

    chip = lgpio.gpiochip_open(0)
    try:
        lgpio.gpio_claim_output(chip, pin)
        lgpio.gpio_write(chip, pin, 0)
        logging.info(f"GPIO initialized: buzzer on pin {pin}")

        consecutive_failures = 0
        fired_today: set     = set()
        last_date_local      = datetime.now(tz=local_tz).date()

        while not _shutdown['requested']:
            try:
                current_date_local = datetime.now(tz=local_tz).date()
                if current_date_local != last_date_local:
                    logging.info(
                        f"New local date ({current_date_local}) — resetting fired trigger list"
                    )
                    fired_today.clear()
                    last_date_local = current_date_local

                next_utc, (sched_h, sched_mn) = _next_trigger(
                    trigger_times, local_tz, grace_sec, fired_today
                )
                sched_local_str = f"{sched_h:02d}:{sched_mn:02d}"
                wait_sec = (next_utc - datetime.now()).total_seconds()

                if wait_sec < 0:
                    logging.info(
                        f"Firing missed trigger: scheduled {sched_local_str} local, "
                        f"{-wait_sec:.0f}s ago — firing now"
                    )
                else:
                    logging.info(
                        f"Next trigger: {sched_local_str} local = "
                        f"{next_utc.strftime('%Y-%m-%d %H:%M')} UTC  "
                        f"(in {wait_sec / 60:.1f} min)"
                    )

                # Sleep in 5s chunks so SIGTERM is caught promptly
                while not _shutdown['requested']:
                    remaining = (next_utc - datetime.now()).total_seconds()
                    if remaining <= 0:
                        break
                    time.sleep(min(remaining, 5.0))

                if _shutdown['requested']:
                    break

                actual_utc_str = datetime.now().strftime('%H:%M:%S')
                seconds_late   = (datetime.now() - next_utc).total_seconds()
                if seconds_late > 2:
                    logging.info(
                        f"Trigger at {actual_utc_str} UTC — scheduled {sched_local_str} local "
                        f"({seconds_late:.0f}s late) — "
                        f"playing {num_seq} sequence(s) of {seq_desc}"
                    )
                else:
                    logging.info(
                        f"Trigger at {actual_utc_str} UTC — scheduled {sched_local_str} local — "
                        f"playing {num_seq} sequence(s) of {seq_desc}"
                    )

                for seq_idx in range(num_seq):
                    if _shutdown['requested']:
                        break
                    t0 = datetime.now()
                    logging.info(
                        f"Sequence {seq_idx + 1}/{num_seq} at {t0.strftime('%H:%M:%S.%f')[:-3]} UTC"
                    )
                    if seq_mode == 'msequence':
                        _play_msequence(chip, pin, pattern, chip_dur)
                    else:
                        _play_beep_sequence(chip, pin, beep_dur, beep_gap, beep_count)

                    if seq_idx < num_seq - 1 and not _shutdown['requested']:
                        time.sleep(gap_btw)

                fired_today.add((sched_h, sched_mn))
                consecutive_failures = 0

            except Exception as e:
                if _shutdown['requested']:
                    break
                consecutive_failures += 1
                logging.error(
                    f"Buzzer loop error (failure {consecutive_failures}/{_MAX_LOOP_FAILURES}): {e}"
                )
                if consecutive_failures >= _MAX_LOOP_FAILURES:
                    logging.error(
                        "Too many consecutive buzzer failures — stopping buzzer controller."
                    )
                    raise
                logging.info(f"Retrying buzzer in {_LOOP_RETRY_DELAY}s...")
                time.sleep(_LOOP_RETRY_DELAY)

    finally:
        lgpio.gpio_write(chip, pin, 0)   # ensure buzzer is OFF on exit
        lgpio.gpiochip_close(chip)
        logging.info("Buzzer controller stopped, GPIO released")


if __name__ == '__main__':
    main()
