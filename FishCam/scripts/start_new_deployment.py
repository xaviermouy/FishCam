#!/usr/bin/env python3
"""
FishCam New Deployment Setup

Walks through all pre-deployment steps in order:
  1. Confirm FishCam unit identity
  2. Configure WittyPi (schedule, RTC sync, voltage thresholds)
  3. Delete all recorded data
  4. Clear the system journal
  5. Reboot (optional but recommended)

Run once before each deployment:
    python3 start_new_deployment.py
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config

SCRIPT_DIR = Path(__file__).parent


def banner(title):
    print()
    print('═' * 68)
    print(f'  {title}')
    print('═' * 68)


def step(n, total, title):
    print()
    print('─' * 68)
    print(f'  Step {n}/{total}: {title}')
    print('─' * 68)


def ask(prompt, valid=('y', 'n'), default=None):
    """Prompt the user for a single-character answer. Returns lowercase char."""
    hint = '/'.join(v.upper() if v == default else v for v in valid)
    while True:
        try:
            answer = input(f'  {prompt} [{hint}]  ').strip().lower()
        except (KeyboardInterrupt, EOFError):
            print('\n  Aborted.')
            sys.exit(0)
        if not answer and default:
            return default
        if answer in valid:
            return answer
        print(f'  Please enter one of: {", ".join(valid)}')


def run_step(cmd, cwd=None):
    """Run a command with full stdin/stdout passthrough. Returns exit code."""
    result = subprocess.run(cmd, cwd=cwd or SCRIPT_DIR)
    return result.returncode


def main():
    banner('FishCam New Deployment Setup')
    print()
    print('  This script prepares the FishCam for a new deployment.')
    print('  Each step will ask for confirmation before making changes.')

    TOTAL_STEPS = 8

    # ── Step 1: Confirm fishcam identity ─────────────────────────────────────
    step(1, TOTAL_STEPS, 'Confirm FishCam identity')
    fishcam_id = config.get_fishcam_id()
    print(f'  FishCam ID (hostname) : {fishcam_id}')
    print()
    answer = ask('Is this the correct unit?', valid=('y', 'n'))
    if answer != 'y':
        print('  Please run this script on the correct unit. Aborting.')
        sys.exit(0)

    # ── Step 2: Confirm deployment timezone ──────────────────────────────────
    step(2, TOTAL_STEPS, 'Confirm deployment timezone')
    tz_name  = config.get_timezone()
    local_tz = None
    try:
        local_tz   = ZoneInfo(tz_name)
        local_now  = datetime.now(tz=local_tz)
        local_time = local_now.strftime('%Y-%m-%d %H:%M:%S')
        offset_str = local_now.strftime('%Z (UTC%z)')
        print(f'  Deployment timezone : {tz_name}')
        print(f'  Current local time  : {local_time}  {offset_str}')
    except ZoneInfoNotFoundError:
        print(f'  WARNING: Timezone "{tz_name}" is not recognized.')
        print(f'  Edit deployment_timezone in fishcam_config.yaml and re-run.')
        answer = ask('Continue anyway?', valid=('y', 'n'), default='n')
        if answer != 'y':
            print('  Aborting.')
            sys.exit(1)
    print()
    answer = ask('Is the timezone and local time correct?', valid=('y', 'n'))
    if answer != 'y':
        print()
        print('  Edit deployment_timezone in fishcam_config.yaml and re-run.')
        sys.exit(0)

    # ── Step 3: Review buzzer schedule ───────────────────────────────────────
    step(3, TOTAL_STEPS, 'Review buzzer schedule')
    buzzer_cfg = config.get_buzzer_settings()
    if not buzzer_cfg.get('enabled', False):
        print('  Buzzer status : DISABLED')
        print()
        answer = ask('Is this intentional?', valid=('y', 'n'))
        if answer != 'y':
            print()
            print('  Set buzzer.enabled: true in fishcam_config.yaml and re-run.')
            sys.exit(0)
    else:
        trigger_times_raw = buzzer_cfg.get('trigger_times', [])
        print(f'  Buzzer status : ENABLED  (GPIO pin {buzzer_cfg["pin"]})')
        print()
        print(f'  {"Local (" + tz_name + ")":<35}  UTC')
        print(f'  {"─" * 35}  {"─" * 5}')
        today = datetime.now(tz=local_tz).date() if local_tz else datetime.utcnow().date()
        for t in trigger_times_raw:
            if local_tz:
                try:
                    h, mn   = map(int, str(t).split(':'))
                    local_dt = datetime(today.year, today.month, today.day,
                                        h, mn, tzinfo=local_tz)
                    utc_str  = local_dt.astimezone(timezone.utc).strftime('%H:%M')
                except Exception:
                    utc_str = '?'
            else:
                utc_str = '(timezone unknown)'
            print(f'  {str(t):<35}  {utc_str}')
        print()
        if buzzer_cfg.get('sequence_mode', 'beep') == 'msequence':
            n            = buzzer_cfg['msequence_n']
            chip_dur     = buzzer_cfg['chip_duration_sec']
            seq_len      = (1 << n) - 1
            seq_duration = seq_len * chip_dur
            print(f'  Sequence mode           : m-sequence')
            print(f'  M-sequence n            : {n}  (sequence length: {seq_len} chips, {seq_duration:.1f}s)')
            print(f'  Chip duration           : {chip_dur}s')
            print(f'  Unit sequence           : derived automatically from hostname')
        else:
            print(f'  Sequence mode           : beep (legacy)')
            print(f'  Beep count per sequence : {buzzer_cfg["beep_count"]}')
        print(f'  Sequences per trigger   : {buzzer_cfg["number_sequences"]}')
        print(f'  Missed trigger grace    : {buzzer_cfg["missed_trigger_grace_sec"]}s')
        print()
        answer = ask('Does the buzzer schedule look correct?', valid=('y', 'n'))
        if answer != 'y':
            print()
            print('  Edit buzzer settings in fishcam_config.yaml and re-run.')
            sys.exit(0)

    # ── Step 4: Configure WittyPi ─────────────────────────────────────────────
    step(4, TOTAL_STEPS, 'Configure WittyPi')
    print('  Running configure_wittypi.py ...')
    print()
    rc = run_step(['python3', 'configure_wittypi.py'])
    if rc != 0:
        print()
        print('  configure_wittypi.py exited with an error.')
        answer = ask('Continue anyway?', valid=('y', 'n'), default='n')
        if answer != 'y':
            print('  Aborting.')
            sys.exit(1)
    print()
    print('  NOTE: If you chose to disable the WittyPi schedule (continuous operation),')
    print('  the WittyPi log will show:')
    print('    "I can not find the begin time in the script..."')
    print('  This is expected — it means WittyPi has no schedule to act on and will')
    print('  leave the Pi running continuously. It is NOT an error.')

    # ── Step 5: Delete recorded data ──────────────────────────────────────────
    step(5, TOTAL_STEPS, 'Delete all recorded data')
    print('  Running delete_data.py ...')
    print()
    rc = run_step(['python3', 'delete_data.py'])
    if rc != 0:
        print()
        print('  delete_data.py exited with an error.')
        answer = ask('Continue anyway?', valid=('y', 'n'), default='n')
        if answer != 'y':
            print('  Aborting.')
            sys.exit(1)

    # ── Step 6: Clear WittyPi logs ────────────────────────────────────────────
    step(6, TOTAL_STEPS, 'Clear WittyPi logs')
    print('  Running clear_wittypi_logs.sh ...')
    print()
    rc = run_step(['bash', 'clear_wittypi_logs.sh'])
    if rc != 0:
        print()
        print('  clear_wittypi_logs.sh exited with an error.')
        answer = ask('Continue anyway?', valid=('y', 'n'), default='n')
        if answer != 'y':
            print('  Aborting.')
            sys.exit(1)

    # ── Step 7: Clear system journal ─────────────────────────────────────────
    step(7, TOTAL_STEPS, 'Clear system journal')
    print('  Running clear_system_logs.sh ...')
    print()
    rc = run_step(['bash', 'clear_system_logs.sh'])
    if rc != 0:
        print()
        print('  clear_system_logs.sh exited with an error.')
        answer = ask('Continue anyway?', valid=('y', 'n'), default='n')
        if answer != 'y':
            print('  Aborting.')
            sys.exit(1)

    # ── Step 8: Reboot ───────────────────────────────────────────────────────
    step(8, TOTAL_STEPS, 'Reboot')
    print('  A reboot is recommended to:')
    print('    - Test the full startup sequence (cron, fishcamStartup.sh)')
    print('    - Apply the WittyPi schedule from cold')
    print('    - Confirm RTC → system clock sync works at boot')
    print()
    answer = ask('Reboot now?', valid=('y', 'n'), default='y')
    if answer == 'y':
        print()
        print('  Rebooting...')
        subprocess.run(['sudo', 'reboot'])
    else:
        print()
        print('  Skipped. Remember to reboot before deploying.')

    print()
    print('=' * 68)
    print('  Deployment setup complete.')
    print('=' * 68)
    print()


if __name__ == '__main__':
    main()
