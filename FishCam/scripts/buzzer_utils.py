#!/usr/bin/env python3
"""
FishCam Buzzer Utilities

Shared functions for parsing and monitoring the buzzer schedule.
Used by both monitor_system.py (dashboard) and run_api.py (HTTP API).

Do NOT import run_buzzer.py from here — it uses lgpio which is hardware-only.
"""

import re
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_trigger_times(time_strings):
    """Parse a list of 'HH:MM' strings into a sorted list of (hour, minute) tuples.

    Unlike run_buzzer._parse_trigger_times, this version silently skips invalid
    entries rather than raising (safe for display / monitoring use).

    Args:
        time_strings: iterable of strings, each expected to match 'HH:MM'

    Returns:
        Sorted list of (h, mn) int tuples.
    """
    times = []
    for ts in time_strings:
        m = re.match(r'^(\d{1,2}):(\d{2})$', str(ts).strip())
        if not m:
            continue
        h, mn = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mn <= 59):
            continue
        times.append((h, mn))
    return sorted(times)


def next_trigger_time(trigger_times, local_tz, grace_sec=0):
    """Return the next trigger time for display purposes.

    Unlike run_buzzer._next_trigger, this function does NOT accept a
    fired_today parameter — it is for display only and always returns the
    next future trigger (or a missed one still within grace, or the first
    trigger tomorrow if all today's triggers are in the past).

    Args:
        trigger_times: sorted list of (h, mn) tuples (from parse_trigger_times)
        local_tz:      ZoneInfo object for the deployment timezone
        grace_sec:     seconds within which a past trigger counts as "missed
                       but still relevant" (0 = disabled)

    Returns:
        (utc_naive_datetime, local_str 'HH:MM', minutes_away float)
        or (None, None, None) if trigger_times is empty.
    """
    if not trigger_times:
        return None, None, None

    now_utc     = datetime.now()                        # naive UTC (Pi always UTC)
    today_local = datetime.now(tz=local_tz).date()

    # 1. Most recently missed trigger within grace window
    if grace_sec > 0:
        for h, mn in reversed(trigger_times):
            local_dt = datetime(today_local.year, today_local.month, today_local.day,
                                h, mn, tzinfo=local_tz)
            utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
            seconds_past = (now_utc - utc_dt).total_seconds()
            if 0 < seconds_past <= grace_sec:
                minutes_away = -seconds_past / 60.0
                return utc_dt, f'{h:02d}:{mn:02d}', minutes_away

    # 2. Next future trigger today
    for h, mn in trigger_times:
        local_dt = datetime(today_local.year, today_local.month, today_local.day,
                            h, mn, tzinfo=local_tz)
        utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        if utc_dt > now_utc:
            minutes_away = (utc_dt - now_utc).total_seconds() / 60.0
            return utc_dt, f'{h:02d}:{mn:02d}', minutes_away

    # 3. All today's triggers are past — first trigger tomorrow
    tomorrow_local = today_local + timedelta(days=1)
    h, mn = trigger_times[0]
    local_dt = datetime(tomorrow_local.year, tomorrow_local.month, tomorrow_local.day,
                        h, mn, tzinfo=local_tz)
    utc_dt   = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    minutes_away = (utc_dt - now_utc).total_seconds() / 60.0
    return utc_dt, f'{h:02d}:{mn:02d}', minutes_away


def get_last_trigger_from_log(log_path):
    """Parse the buzzer log file to find the most recently fired trigger.

    Looks for lines matching either:
      "Trigger at 15:40:02 UTC — scheduled 11:40 local"
      "Firing missed trigger: scheduled 15:40 local"

    Args:
        log_path: Path or str to the buzzer log file.

    Returns:
        (last_local_str, last_utc_str) both as strings, or (None, None)
        if the log is missing / empty / no trigger lines found.
        last_utc_str is None for missed-trigger lines (no UTC time logged).
    """
    try:
        with open(log_path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return None, None
            # Read last 32 KB — enough for many log entries
            f.seek(-min(size, 32768), 2)
            lines = f.read().decode(errors='replace').splitlines()
    except (FileNotFoundError, OSError):
        return None, None

    # Patterns (search in reverse order to find the most recent)
    # "Trigger at 15:40:02 UTC — scheduled 11:40 local"
    pat_fired  = re.compile(
        r'Trigger at (\d{2}:\d{2}:\d{2}) UTC.*scheduled (\d{2}:\d{2}) local'
    )
    # "Firing missed trigger: scheduled 15:40 local"
    pat_missed = re.compile(
        r'Firing missed trigger.*scheduled (\d{2}:\d{2}) local'
    )

    for line in reversed(lines):
        m = pat_fired.search(line)
        if m:
            return m.group(2), m.group(1)   # (local_str, utc_str)
        m = pat_missed.search(line)
        if m:
            return m.group(1), None         # local only; no UTC in missed log line

    return None, None


def get_buzzer_status(buzzer_cfg, log_path):
    """Build a buzzer status dict for the dashboard and API.

    Args:
        buzzer_cfg: dict returned by config.get_buzzer_settings()
        log_path:   Path to the buzzer log file (e.g. log_dir / 'buzzer_fishcam01.log')

    Returns:
        dict with keys:
            enabled      (bool)
            trigger_times (list of 'HH:MM' strings)
            next_local   ('HH:MM' or None)
            next_utc     ('HH:MM' or None)
            next_in_min  (float or None)
            last_local   (str or None)
            last_utc     (str or None)
    """
    enabled       = bool(buzzer_cfg.get('enabled', False))
    raw_times     = buzzer_cfg.get('trigger_times', [])
    grace_sec     = buzzer_cfg.get('missed_trigger_grace_sec', 0)
    tz_name       = buzzer_cfg.get('deployment_timezone', 'UTC')

    trigger_tuples = parse_trigger_times(raw_times)
    trigger_strs   = [f'{h:02d}:{mn:02d}' for h, mn in trigger_tuples]

    next_local = next_utc_str = next_in_min = None
    if enabled and trigger_tuples:
        try:
            local_tz = ZoneInfo(tz_name)
            next_utc_dt, next_local, next_in_min = next_trigger_time(
                trigger_tuples, local_tz, grace_sec
            )
            if next_utc_dt is not None:
                next_utc_str = next_utc_dt.strftime('%H:%M')
        except Exception:
            pass

    last_local, last_utc = get_last_trigger_from_log(log_path)

    return {
        'enabled':      enabled,
        'trigger_times': trigger_strs,
        'next_local':   next_local,
        'next_utc':     next_utc_str,
        'next_in_min':  next_in_min,
        'last_local':   last_local,
        'last_utc':     last_utc,
    }
