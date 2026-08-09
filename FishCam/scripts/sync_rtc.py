#!/usr/bin/env python3
"""
FishCam RTC Sync from Internet (NTP)

Called once at boot by fishcamStartup.sh, after run_network.py has
had a chance to bring WiFi up.

If the system clock is NTP-synchronized, pushes the accurate time to
the WittyPi RTC so it stays correct across power cycles.

Skips immediately (no waiting) if:
  - auto_sync_rtc_from_internet is disabled in config
  - WiFi interface is not up (i.e. power saving mode at boot, or no network)
  - Last RTC sync (from any source) was less than rtc_sync_min_interval_min ago

If WiFi is up but NTP has not yet synced, retries up to MAX_NTP_ATTEMPTS
times with NTP_RETRY_DELAY_S between attempts before giving up.

GPS time sync is handled separately by run_gps.py (future), controlled
by the auto_sync_rtc_from_gps flag in fishcam_config.yaml.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import config
from wittypi_utils import (
    sync_rtc_from_system,
    is_rtc_sync_due,
    record_rtc_sync,
    get_rtc_sync_state_path,
    is_wifi_up,
    is_ntp_synced,
)

MAX_NTP_ATTEMPTS  = 3
NTP_RETRY_DELAY_S = 20


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        wittypi_cfg = config.get_wittypi_settings()
        paths       = config.get_paths()
    except Exception as e:
        logging.error(f"sync_rtc: failed to load config: {e}")
        sys.exit(1)

    # ── Guard: feature enabled? ───────────────────────────────────────────────
    if not wittypi_cfg['auto_sync_rtc_from_internet']:
        logging.info("sync_rtc: auto_sync_rtc_from_internet disabled — skipping")
        return

    # ── Guard: WiFi up? (instant skip — no waiting) ───────────────────────────
    if not is_wifi_up():
        logging.info("sync_rtc: WiFi not up — skipping internet RTC sync")
        return

    # ── Guard: minimum interval since last sync ───────────────────────────────
    script_dir  = Path(__file__).parent
    log_dir     = script_dir / paths['log_dir']
    log_dir.mkdir(parents=True, exist_ok=True)
    state_file  = get_rtc_sync_state_path(log_dir)
    min_interval = wittypi_cfg['rtc_sync_min_interval_min']

    if not is_rtc_sync_due(state_file, min_interval):
        logging.info(
            f"sync_rtc: last RTC sync was less than {min_interval} min ago — skipping"
        )
        return

    # ── Wait for NTP sync, then update RTC ───────────────────────────────────
    install_dir = wittypi_cfg['install_dir']

    for attempt in range(1, MAX_NTP_ATTEMPTS + 1):
        if is_ntp_synced():
            ok, msg = sync_rtc_from_system(install_dir)
            if ok:
                record_rtc_sync(state_file)
                logging.info(f"sync_rtc: {msg}")
            else:
                logging.error(f"sync_rtc: {msg}")
            return

        if attempt < MAX_NTP_ATTEMPTS:
            logging.info(
                f"sync_rtc: NTP not yet synced "
                f"(attempt {attempt}/{MAX_NTP_ATTEMPTS}) — "
                f"retrying in {NTP_RETRY_DELAY_S}s"
            )
            time.sleep(NTP_RETRY_DELAY_S)

    logging.warning(
        f"sync_rtc: NTP not synced after {MAX_NTP_ATTEMPTS} attempts — "
        f"skipping RTC update"
    )


if __name__ == '__main__':
    main()
