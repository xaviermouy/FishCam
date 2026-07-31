#!/usr/bin/env python3
"""
FishCam WittyPi Configuration Script

Run once before each deployment (interactively, with sudo):

  1. Verifies system prerequisites (UTC timezone, NTP sync, WittyPi detected)
  2. Asks whether to apply a power schedule or disable scheduling entirely
  3. Validates the wittypi section of fishcam_config.yaml (schedule mode only)
  4. Shows a visual 24-hour schedule preview for confirmation (schedule mode only)
  5. Synchronises the WittyPi RTC from the system clock
  6. Generates and loads the power schedule (or always-on schedule) into WittyPi
  7. Writes voltage protection thresholds and power-cut delay via I2C

Usage:
    sudo python3 configure_wittypi.py              # interactive — asks for mode
    sudo python3 configure_wittypi.py --disable    # skip prompt, disable schedule

NOTE: Do NOT add this script to fishcamStartup.sh. Run it manually once
before each deployment to configure WittyPi with the correct schedule.

GPS time sync note: when a GPS module is added, the sync_rtc_from_system()
function defined here can be called by run_gps.py after obtaining a valid
fix to keep the RTC accurate during deployment.
"""

import sys
import argparse
import difflib
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import config

# ─── WittyPi I2C register addresses ───────────────────────────────────────────
# ⚠  VERIFY these against /home/fishcam/wittypi/utilities.sh before relying on
#    them. They are based on WittyPi 4 documentation and may differ for v4 mini.
#    If I2C writes fail, set parameters manually via the wittyPi.sh menu.
I2C_BUS              = 1
I2C_MC_ADDR          = None       # loaded from config (typically 0x08)
REG_POWER_CUT_DELAY  = 0x09      # ← verify: power-cut delay (units: seconds)
REG_LOW_VOLTAGE      = 0x0B      # ← verify: low-voltage cutoff (units: 0.1 V)
REG_RECOVERY_VOLTAGE = 0x0C      # ← verify: recovery voltage  (units: 0.1 V)

SCHEDULE_FILENAME    = 'schedule.wpi'
TIMELINE_CHARS       = 72          # width of the 24 h bar (1 char = 20 min)
_MINS_PER_CHAR       = (24 * 60) // TIMELINE_CHARS  # = 20


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def _fmt_minutes(total_min):
    """Format a minute count as '3h 25m', '45m', etc."""
    h, m = divmod(int(total_min), 60)
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _print_check(ok, msg, warn=False):
    marker = '[✓]' if ok else ('[!]' if warn else '[✗]')
    print(f"  {marker} {msg}")


# ─── Prerequisite checks ──────────────────────────────────────────────────────

def check_utc_timezone():
    r = _run("timedatectl show --property=Timezone --value")
    tz = r.stdout.strip()
    # Accept all equivalent UTC zone names
    if tz in ('UTC', 'Etc/UTC', 'UTC0', 'Universal', 'Zulu'):
        return True, f"System timezone is UTC ({tz})"
    return False, (
        f"System timezone is '{tz}' — must be UTC. "
        f"Fix with: sudo timedatectl set-timezone UTC"
    )


def check_ntp_sync():
    r = _run("timedatectl show --property=NTPSynchronized --value")
    ok = r.stdout.strip().lower() == 'yes'
    if ok:
        return True, "System clock is NTP-synchronized"
    return False, "System clock is NOT NTP-synchronized — RTC may be set to wrong time"


def check_wittypi_i2c(addr):
    r = _run("i2cdetect -y 1")
    if r.returncode != 0:
        return False, f"i2cdetect failed: {r.stderr.strip()}"
    if f"{addr:02x}" in r.stdout.lower():
        return True, f"WittyPi detected on I2C bus 1 at 0x{addr:02X}"
    return False, f"WittyPi NOT detected on I2C bus 1 at 0x{addr:02X}"


def check_scripts(install_dir):
    results = []
    for name in ('syncTime.sh', 'runScript.sh'):
        p = Path(install_dir) / name
        ok = p.exists()
        msg = f"Found {name}" if ok else f"Missing: {p}"
        results.append((ok, msg))
    return results


def validate_timezone(tz_name):
    """Return (ZoneInfo, None) on success, or (None, [suggestions]) on failure."""
    try:
        return ZoneInfo(tz_name), None
    except ZoneInfoNotFoundError:
        suggestions = difflib.get_close_matches(
            tz_name, sorted(available_timezones()), n=5, cutoff=0.5
        )
        return None, suggestions


def check_windows(windows):
    total = sum(w['duration_hours'] for w in windows)
    if abs(total - 24.0) < 0.001:
        parts = ' + '.join(f"{w['name']} {w['duration_hours']}h" for w in windows)
        return True, f"Daily windows sum to 24h  ({parts})"
    return False, f"Daily windows sum to {total}h — must be exactly 24h"


def check_dst(deploy_start_local, deploy_end_local):
    """Return (has_transition, offset_at_start, offset_at_end)."""
    off_start = deploy_start_local.utcoffset()
    off_end   = deploy_end_local.utcoffset()
    return off_start != off_end, off_start, off_end


def check_voltage(low_v, rec_v):
    if low_v == 0 and rec_v == 0:
        return True, "Voltage protection disabled (set both to non-zero to enable)"
    if (low_v == 0) != (rec_v == 0):
        return False, "Both low_voltage_cutoff_v and recovery_voltage_v must be 0, or both non-zero"
    if rec_v <= low_v:
        return False, f"recovery_voltage_v ({rec_v} V) must be > low_voltage_cutoff_v ({low_v} V)"
    return True, f"Voltage protection: cutoff {low_v} V, recovery {rec_v} V"


def check_power_cut_delay(delay_s):
    if delay_s < 30:
        return False, (
            f"power_cut_delay_sec={delay_s}s is too short — "
            f"Pi needs ≥ 30 s to shut down cleanly (60 s recommended)"
        )
    if delay_s < 45:
        return True, f"power_cut_delay_sec={delay_s}s — marginal; 60 s recommended"
    return True, f"power_cut_delay_sec={delay_s}s"


# ─── Schedule computation ─────────────────────────────────────────────────────

def compute_anchor_utc(deploy_start_str, anchor_time_str, tz):
    """Return the first occurrence of anchor_time on or after deploy_start, in UTC."""
    deploy_start = datetime.strptime(deploy_start_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
    h, m = map(int, anchor_time_str.split(':'))
    anchor = deploy_start.replace(hour=h, minute=m, second=0, microsecond=0)
    if anchor < deploy_start:
        anchor += timedelta(days=1)
    return anchor.astimezone(timezone.utc)


def build_entries(windows):
    """Convert YAML windows to a flat list of (kind, minutes) pairs summing to 1440 min."""
    entries = []
    for w in windows:
        win_min = round(w['duration_hours'] * 60)
        on_min  = w['on_min']
        off_min = w['off_min']

        if off_min == 0:
            # Continuous recording for the whole window
            entries.append(('ON', win_min))
            continue

        cycle    = on_min + off_min
        n_full   = win_min // cycle
        remain   = win_min % cycle

        for _ in range(n_full):
            entries.append(('ON',  on_min))
            entries.append(('OFF', off_min))

        if remain:
            # Pad the end of the window with an OFF block so windows stay aligned
            entries.append(('OFF', remain))

    return entries


def generate_schedule_content(anchor_utc, deploy_end_utc, entries):
    """Return the WittyPi .wpi schedule file content as a string."""
    lines = [
        f"BEGIN {anchor_utc.strftime('%Y-%m-%d %H:%M:%S')}",
        f"END   {deploy_end_utc.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    for kind, minutes in entries:
        h, m = divmod(minutes, 60)
        lines.append(f"{kind:<5} H{h} M{m} S0")
    return '\n'.join(lines) + '\n'


def _window_stats(windows):
    """Compute per-window display stats."""
    stats = []
    for w in windows:
        win_min = round(w['duration_hours'] * 60)
        on_min  = w['on_min']
        off_min = w['off_min']
        if off_min == 0:
            n_cycles = 1
            on_total = win_min
        else:
            n_cycles = win_min // (on_min + off_min)
            on_total = n_cycles * on_min
        stats.append({
            'name':     w['name'],
            'win_min':  win_min,
            'on_min':   on_min,
            'off_min':  off_min,
            'n_cycles': n_cycles,
            'on_total': on_total,
            'duty':     on_total / win_min * 100,
        })
    return stats


# ─── Terminal visualization ───────────────────────────────────────────────────

def _entries_to_slots(entries):
    """Return 72 ON-fraction values (0.0–1.0), one per 20-min slot."""
    per_min = []
    for kind, dur in entries:
        per_min.extend([kind == 'ON'] * dur)
    # Pad or trim to exactly 1440 minutes
    per_min = (per_min + [False] * 1440)[:1440]

    slots = []
    for i in range(TIMELINE_CHARS):
        s = i * _MINS_PER_CHAR
        e = s + _MINS_PER_CHAR
        slots.append(sum(per_min[s:e]) / _MINS_PER_CHAR)
    return slots


def _frac_to_char(f):
    if f == 0.0: return '░'
    if f < 0.5:  return '▒'
    if f < 1.0:  return '▓'
    return '█'


def _time_axis(anchor_h, anchor_m, label):
    """Build a one-line time axis with labels every 4 hours (every 12 chars)."""
    buf = [' '] * TIMELINE_CHARS
    for i in range(7):                         # 7 ticks: 0h, 4h, 8h, ..., 24h
        pos = i * 12
        if pos >= TIMELINE_CHARS:
            break
        total_mins = anchor_h * 60 + anchor_m + i * 240
        h = (total_mins // 60) % 24
        m = total_mins % 60
        label_str = f"{h:02d}:{m:02d}"
        for j, ch in enumerate(label_str):
            if pos + j < TIMELINE_CHARS:
                buf[pos + j] = ch
    return f"  {label:<7} " + ''.join(buf)


def _tick_row():
    buf = [' '] * TIMELINE_CHARS
    for i in range(7):
        pos = i * 12
        if pos < TIMELINE_CHARS:
            buf[pos] = '|'
    return "  " + ' ' * 8 + ''.join(buf)


def _bracket_row(windows):
    """Build a row of labelled window brackets below the bar."""
    parts = []
    for w in windows:
        n     = round(w['duration_hours'] * 60 / _MINS_PER_CHAR)
        name  = w['name']
        inner = n - 2
        if inner <= 0:
            parts.append('─' * n)
        elif len(name) <= inner:
            parts.append('[' + name.center(inner, '─') + ']')
        else:
            parts.append('[' + name[:inner] + ']')
    return "  " + ' ' * 8 + ''.join(parts)


def visualize_schedule(wittypi_cfg, tz, anchor_utc, entries):
    """Print the 24-hour timeline and summary table."""
    windows    = wittypi_cfg['daily_schedule']['windows']
    anchor_str = wittypi_cfg['daily_schedule']['anchor_time']
    ah, am     = map(int, anchor_str.split(':'))

    deploy_start_local = datetime.strptime(
        wittypi_cfg['deployment']['start'], '%Y-%m-%d %H:%M:%S'
    ).replace(tzinfo=tz)
    off_sec = deploy_start_local.utcoffset().total_seconds()
    off_h   = int(off_sec / 3600)
    off_m   = int((abs(off_sec) % 3600) / 60)
    if off_m:
        off_str = f"UTC{off_h:+d}:{off_m:02d}"
    else:
        off_str = f"UTC{off_h:+d}" if off_h else "UTC"

    slots = _entries_to_slots(entries)
    bar   = ''.join(_frac_to_char(f) for f in slots)

    print()
    print("─" * 78)
    print("  24-HOUR POWER SCHEDULE PREVIEW")
    print("─" * 78)
    print(f"  Timezone : {wittypi_cfg['timezone']}  ({off_str} at deployment start)")
    print(f"  Anchor   : {anchor_str} local  =  "
          f"{anchor_utc.strftime('%H:%M')} UTC")
    print()
    print(_time_axis(ah, am, 'Local'))
    print(_time_axis(anchor_utc.hour, anchor_utc.minute, 'UTC'))
    print(_tick_row())
    print("  " + ' ' * 8 + bar)
    print(_bracket_row(windows))
    print()
    print("  Legend:  █ ON    ▓ mostly ON    ▒ partial    ░ mostly OFF")
    print()

    # ── Summary table ────────────────────────────────────────────────────────
    stats     = _window_stats(windows)
    total_on  = sum(s['on_total'] for s in stats)
    total_cyc = sum(s['n_cycles'] for s in stats)

    col = f"  {'Window':<14} {'Local':<13} {'UTC':<13} {'Cycle':<13} " \
          f"{'Cycles':>6}  {'ON/day':>7}  {'Duty':>5}"
    print(col)
    print("  " + "─" * 72)

    elapsed_min = 0
    for s, w in zip(stats, windows):
        loc_s_h = (ah * 60 + am + elapsed_min) // 60 % 24
        loc_s_m = (ah * 60 + am + elapsed_min) % 60
        loc_e_h = (ah * 60 + am + elapsed_min + s['win_min']) // 60 % 24
        loc_e_m = (ah * 60 + am + elapsed_min + s['win_min']) % 60

        utc_base = anchor_utc.hour * 60 + anchor_utc.minute
        utc_s_h  = (utc_base + elapsed_min) // 60 % 24
        utc_s_m  = (utc_base + elapsed_min) % 60
        utc_e_h  = (utc_base + elapsed_min + s['win_min']) // 60 % 24
        utc_e_m  = (utc_base + elapsed_min + s['win_min']) % 60

        loc_range = f"{loc_s_h:02d}:{loc_s_m:02d}–{loc_e_h:02d}:{loc_e_m:02d}"
        utc_range = f"{utc_s_h:02d}:{utc_s_m:02d}–{utc_e_h:02d}:{utc_e_m:02d}"
        cycle_str = "continuous" if s['off_min'] == 0 else f"{s['on_min']}m/{s['off_min']}m"

        print(f"  {s['name']:<14} {loc_range:<13} {utc_range:<13} {cycle_str:<13} "
              f"{s['n_cycles']:>6}  {_fmt_minutes(s['on_total']):>7}  {s['duty']:>4.0f}%")
        elapsed_min += s['win_min']

    print("  " + "─" * 72)
    total_duty = total_on / (24 * 60) * 100
    print(f"  {'Total':<14} {'':<13} {'':<13} {'':<13} "
          f"{total_cyc:>6}  {_fmt_minutes(total_on):>7}  {total_duty:>4.0f}%")

    # Sequence sanity check
    total_seq_min = sum(m for _, m in entries)
    ok_str = "✓" if total_seq_min == 1440 else f"✗  ({total_seq_min} min ≠ 1440)"
    n_on  = sum(1 for k, _ in entries if k == 'ON')
    n_off = sum(1 for k, _ in entries if k == 'OFF')
    print()
    print(f"  WittyPi sequence: {n_on} ON + {n_off} OFF blocks, "
          f"total = {total_seq_min // 60}h {total_seq_min % 60}m  {ok_str}")
    print("─" * 78)


# ─── Always-on schedule ───────────────────────────────────────────────────────

def generate_always_on_schedule():
    """Return a .wpi schedule that keeps the Pi on indefinitely.

    A single 24-hour ON block repeating from a past BEGIN date effectively
    disables power cycling — WittyPi will never cut power on its own.
    """
    return (
        "BEGIN 2000-01-01 00:00:00\n"
        "END   2099-12-31 23:59:59\n"
        "ON    H24 M0 S0\n"
    )


# ─── WittyPi operations ───────────────────────────────────────────────────────

def sync_rtc_from_system(install_dir):
    """Synchronise the WittyPi RTC from the system clock via syncTime.sh.

    This function is intentionally standalone so that a future run_gps.py can
    call it after obtaining a valid GPS fix to keep the RTC accurate during
    deployment without needing to re-run the full setup script.
    """
    r = subprocess.run(
        ['sudo', 'bash', 'syncTime.sh'],
        cwd=install_dir, capture_output=True, text=True
    )
    if r.returncode == 0:
        return True, "WittyPi RTC synchronised from system clock"
    return False, f"syncTime.sh failed: {(r.stderr or r.stdout).strip()}"


def save_and_load_schedule(install_dir, content):
    """Write schedule.wpi and load it into WittyPi via runScript.sh."""
    schedule_path = Path(install_dir) / SCHEDULE_FILENAME
    try:
        schedule_path.write_text(content)
    except OSError as e:
        return False, f"Failed to write {schedule_path}: {e}"

    r = subprocess.run(
        ['sudo', 'bash', 'runScript.sh'],
        cwd=install_dir, capture_output=True, text=True
    )
    if r.returncode == 0:
        return True, f"Schedule written to {schedule_path} and loaded into WittyPi"
    return False, f"runScript.sh failed: {(r.stderr or r.stdout).strip()}"


def _i2cset(addr, reg, value):
    """Write one byte to an I2C register via i2cset."""
    r = _run(f"i2cset -y {I2C_BUS} {addr:#04x} {reg:#04x} {value:#04x}")
    return r.returncode == 0, r.stderr.strip()


def write_i2c_params(wittypi_cfg):
    """Write power-cut delay and voltage thresholds to WittyPi registers.

    Returns a list of (ok, message) tuples — one per parameter written.

    ⚠  Register addresses at the top of this file need to be verified against
       /home/fishcam/wittypi/utilities.sh for the WittyPi v4 mini.
       If any write fails, set the parameter manually via the wittyPi.sh menu.
    """
    results = []
    addr    = wittypi_cfg['i2c_address']
    delay_s = wittypi_cfg.get('power_cut_delay_sec', 60)
    low_v   = wittypi_cfg.get('low_voltage_cutoff_v', 0)
    rec_v   = wittypi_cfg.get('recovery_voltage_v', 0)

    # Power-cut delay
    ok, err = _i2cset(addr, REG_POWER_CUT_DELAY, min(delay_s, 255))
    results.append((ok,
        f"Power-cut delay {delay_s}s → reg 0x{REG_POWER_CUT_DELAY:02X} = {min(delay_s, 255)}"
        + ('' if ok else f"  FAILED: {err}")
    ))

    # Voltage protection
    if low_v == 0 and rec_v == 0:
        results.append((True, "Voltage protection disabled — skipping I2C writes"))
    else:
        raw_low = round(low_v * 10)
        raw_rec = round(rec_v * 10)
        ok, err = _i2cset(addr, REG_LOW_VOLTAGE, raw_low)
        results.append((ok,
            f"Low-voltage cutoff {low_v} V → reg 0x{REG_LOW_VOLTAGE:02X} = {raw_low}"
            + ('' if ok else f"  FAILED: {err}")
        ))
        ok, err = _i2cset(addr, REG_RECOVERY_VOLTAGE, raw_rec)
        results.append((ok,
            f"Recovery voltage {rec_v} V → reg 0x{REG_RECOVERY_VOLTAGE:02X} = {raw_rec}"
            + ('' if ok else f"  FAILED: {err}")
        ))

    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # ── Parse arguments ──────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description='Configure WittyPi power schedule for FishCam deployment.'
    )
    parser.add_argument(
        '--disable',
        action='store_true',
        help='Disable WittyPi power scheduling (Pi stays on continuously). '
             'Skips the interactive mode prompt.'
    )
    args = parser.parse_args()

    print()
    print("=" * 78)
    print("  FishCam WittyPi Configuration")
    print("=" * 78)

    # ── Load config ──────────────────────────────────────────────────────────
    try:
        wittypi_cfg = config.get_wittypi_settings()
    except Exception as e:
        print(f"\n  ERROR: Failed to load configuration: {e}")
        sys.exit(1)

    install_dir  = wittypi_cfg['install_dir']
    i2c_addr     = wittypi_cfg['i2c_address']
    delay_s      = wittypi_cfg['power_cut_delay_sec']
    low_v        = wittypi_cfg['low_voltage_cutoff_v']
    rec_v        = wittypi_cfg['recovery_voltage_v']
    tz_name      = wittypi_cfg['timezone']
    windows      = wittypi_cfg['daily_schedule']['windows']
    anchor_str   = wittypi_cfg['daily_schedule']['anchor_time']
    deploy_start = wittypi_cfg['deployment']['start']
    deploy_end   = wittypi_cfg['deployment']['end']

    # ── Prerequisite checks (common to both modes) ───────────────────────────
    print()
    print("  PREREQUISITE CHECKS")
    print("  " + "─" * 50)

    critical_fail = False

    ok, msg = check_utc_timezone()
    _print_check(ok, msg)
    critical_fail |= not ok

    ok, msg = check_ntp_sync()
    _print_check(ok, msg, warn=not ok)  # warning only — don't hard-stop

    ok, msg = check_wittypi_i2c(i2c_addr)
    _print_check(ok, msg)
    critical_fail |= not ok

    for ok, msg in check_scripts(install_dir):
        _print_check(ok, msg)
        critical_fail |= not ok

    ok, msg = check_voltage(low_v, rec_v)
    _print_check(ok, msg)
    critical_fail |= not ok

    ok, msg = check_power_cut_delay(delay_s)
    _print_check(ok, msg, warn=not ok)
    critical_fail |= not ok

    if critical_fail:
        print()
        print("  One or more critical checks failed. Fix the issues above and re-run.")
        sys.exit(1)

    # ── Mode selection ───────────────────────────────────────────────────────
    if args.disable:
        disable_schedule = True
    else:
        print()
        print("  SCHEDULE MODE")
        print("  " + "─" * 50)
        print("    [1] Apply power schedule from fishcam_config.yaml")
        print("    [2] Disable schedule  (Pi stays on continuously)")
        print()
        try:
            choice = input("  Choice [1/2]:  ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Aborted.")
            sys.exit(0)
        if choice == '2':
            disable_schedule = True
        elif choice == '1':
            disable_schedule = False
        else:
            print("  Invalid choice — aborted.")
            sys.exit(0)

    # ── Schedule mode: validate and visualize ────────────────────────────────
    if not disable_schedule:
        print()
        print("  SCHEDULE CHECKS")
        print("  " + "─" * 50)

        tz, suggestions = validate_timezone(tz_name)
        if tz is None:
            print(f"\n  [✗] Timezone '{tz_name}' not recognized.")
            if suggestions:
                print("      Did you mean one of these?")
                for s in suggestions:
                    print(f"          {s}")
            print("      Edit 'timezone' in fishcam_config.yaml and re-run.")
            sys.exit(1)

        deploy_start_local = datetime.strptime(deploy_start, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
        deploy_end_local   = datetime.strptime(deploy_end,   '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
        off_sec = deploy_start_local.utcoffset().total_seconds()
        off_h   = int(off_sec / 3600)
        off_str = f"UTC{off_h:+d}" if off_h else "UTC"
        _print_check(True, f"Timezone '{tz_name}' recognized  ({off_str} at deployment start)")

        ok, msg = check_windows(windows)
        _print_check(ok, msg)
        if not ok:
            print("\n  Schedule check failed. Fix the issues above and re-run.")
            sys.exit(1)

        has_dst, off_start, off_end = check_dst(deploy_start_local, deploy_end_local)
        if has_dst:
            _print_check(False,
                f"Deployment spans a DST transition ({off_start} → {off_end}) — "
                f"schedule will drift by the offset change after the transition",
                warn=True)
        else:
            _print_check(True, "No DST transition within deployment window")

        # Build and show schedule
        anchor_utc     = compute_anchor_utc(deploy_start, anchor_str, tz)
        deploy_end_utc = deploy_end_local.astimezone(timezone.utc)
        entries        = build_entries(windows)
        schedule_text  = generate_schedule_content(anchor_utc, deploy_end_utc, entries)

        visualize_schedule(wittypi_cfg, tz, anchor_utc, entries)

        print()
        print("  SCHEDULE FILE  (→ will be written to schedule.wpi)")
        print("  " + "─" * 50)
        for line in schedule_text.strip().splitlines():
            print(f"    {line}")
        print()

        try:
            answer = input("  Apply this schedule to WittyPi? [y/N]  ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n  Aborted.")
            sys.exit(0)
        if answer != 'y':
            print("  Aborted — no changes made to WittyPi.")
            sys.exit(0)

    # ── Disable mode: confirm ────────────────────────────────────────────────
    else:
        schedule_text = generate_always_on_schedule()
        print()
        print("  DISABLE SCHEDULE")
        print("  " + "─" * 50)
        print("  WittyPi will be configured to keep the Pi on continuously.")
        print("  Power cycling is disabled until configure_wittypi.py is re-run")
        print("  with a schedule.")
        print()
        try:
            answer = input("  Disable WittyPi schedule? [y/N]  ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n  Aborted.")
            sys.exit(0)
        if answer != 'y':
            print("  Aborted — no changes made to WittyPi.")
            sys.exit(0)

    # ── Apply (both modes) ───────────────────────────────────────────────────
    print()
    print("  APPLYING CONFIGURATION")
    print("  " + "─" * 50)

    ok, msg = sync_rtc_from_system(install_dir)
    _print_check(ok, msg)
    if not ok:
        print("  RTC sync failed — aborting. Check that syncTime.sh is present and sudo works.")
        sys.exit(1)

    ok, msg = save_and_load_schedule(install_dir, schedule_text)
    _print_check(ok, msg)
    if not ok:
        print("  Schedule loading failed — aborting. Check that runScript.sh is present.")
        sys.exit(1)

    i2c_results = write_i2c_params(wittypi_cfg)
    i2c_all_ok  = True
    for ok, msg in i2c_results:
        _print_check(ok, msg, warn=not ok)
        i2c_all_ok &= ok

    # ── Final summary ────────────────────────────────────────────────────────
    print()
    print("─" * 78)
    print("  CONFIGURATION COMPLETE")
    print("─" * 78)

    if disable_schedule:
        print("  Mode           : Schedule DISABLED — Pi stays on continuously")
    else:
        deployment_days = (deploy_end_local - deploy_start_local).days
        print(f"  Mode           : Schedule active")
        print(f"  First power-on : {anchor_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"
              f"  ({deploy_start_local.strftime('%Y-%m-%d %H:%M')} local)")
        print(f"  Schedule end   : {deploy_end_local.strftime('%Y-%m-%d %H:%M')} local"
              f"  →  {deploy_end_utc.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"  Deployment     : {deployment_days} days")

    print(f"  Power-cut delay: {delay_s} s  "
          f"(Pi has this long to finish shutting down after SIGTERM)")

    if not i2c_all_ok:
        print()
        print("  ⚠  One or more I2C parameter writes failed.")
        print("     Set them manually via the wittyPi.sh menu.")
        print("     Also verify register addresses in configure_wittypi.py against")
        print("     /home/fishcam/wittypi/utilities.sh for the WittyPi v4 mini.")

    print("─" * 78)
    print()


if __name__ == '__main__':
    main()
