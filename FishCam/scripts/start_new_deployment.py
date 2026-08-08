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
from datetime import datetime
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

    TOTAL_STEPS = 7

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
    tz_name = config.get_timezone()
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

    # ── Step 3: Configure WittyPi ─────────────────────────────────────────────
    step(3, TOTAL_STEPS, 'Configure WittyPi')
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

    # ── Step 4: Delete recorded data ──────────────────────────────────────────
    step(4, TOTAL_STEPS, 'Delete all recorded data')
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

    # ── Step 5: Clear WittyPi logs ────────────────────────────────────────────
    step(5, TOTAL_STEPS, 'Clear WittyPi logs')
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

    # ── Step 6: Clear system journal ─────────────────────────────────────────
    step(6, TOTAL_STEPS, 'Clear system journal')
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

    # ── Step 7: Reboot ───────────────────────────────────────────────────────
    step(7, TOTAL_STEPS, 'Reboot')
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
