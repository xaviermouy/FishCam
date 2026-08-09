#!/usr/bin/env python3
"""
FishCam System Monitor

Live dashboard showing the status of all FishCam processes, recent log
activity, hardware health, storage, and system state. Designed to run
over SSH — no display hardware required.

Usage (from the scripts directory):
    python3 monitor_system.py

Controls:
    r / R    — force immediate refresh
    q / Esc  — quit
"""

import curses
import sys
import time
from pathlib import Path

import config
from system_status import (
    collect, PROCESSES,
    find_process, fmt_uptime,
    tail_bytes, last_notable, count_recent_errors,
    check_camera, read_wittypi_voltage, check_i2c,
    cpu_temp, cpu_freq_mhz, wifi_status, system_uptime,
    storage_info,
)


# ── Constants ─────────────────────────────────────────────────────────────────

REFRESH_INTERVAL = 10   # seconds between auto-refreshes


# ── Rendering ─────────────────────────────────────────────────────────────────

def put(stdscr, row, col, text, attr, W):
    max_rows, _ = stdscr.getmaxyx()
    if row >= max_rows - 1:
        return
    try:
        stdscr.addstr(row, col, str(text)[:max(0, W - col)], attr)
    except curses.error:
        pass


def render(stdscr, data, secs_to_refresh, C):
    stdscr.erase()
    _, W = stdscr.getmaxyx()
    r = 0

    def p(row, col, text, attr=0):
        put(stdscr, row, col, text, attr, W)

    def hr(row):
        p(row, 0, '─' * W)

    BOLD   = curses.A_BOLD
    GREEN  = C['green']
    RED    = C['red']
    YELLOW = C['yellow']
    CYAN   = C['cyan']

    # ── Header ──────────────────────────────────────────────────────────────
    ts = data['time']   # already a string from collect()
    p(r, 0, '═' * W, BOLD); r += 1
    p(r, 0, f'  FishCam System Monitor  │  {data["fishcam_id"]}  │  {ts}  │  [r]efresh  [q]uit', BOLD | CYAN); r += 1
    p(r, 0, '═' * W, BOLD); r += 1

    # ── Processes ────────────────────────────────────────────────────────────
    p(r, 0, '  PROCESSES', BOLD); r += 1
    hr(r); r += 1

    for proc in data['processes']:
        label = f'  {proc["label"]:<18}'
        p(r, 0, label, BOLD)
        if proc['running']:
            p(r, len(label), f'✓ RUNNING   PID {proc["pid"]:<7} up {proc["uptime"]}', GREEN | BOLD)
        else:
            p(r, len(label), '✗ STOPPED', RED | BOLD)
        r += 1

    # ── Acquisition ──────────────────────────────────────────────────────────
    p(r, 0, '  ACQUISITION', BOLD); r += 1
    hr(r); r += 1

    acq = data.get('acquisition', {})

    # Determine process running state for video and IMU (to colour correctly)
    proc_running = {proc['label']: proc['running'] for proc in data['processes']}

    for key, label, proc_label in [
        ('video', 'Video ', 'Video'),
        ('imu',   'IMU   ', 'IMU'),
    ]:
        info      = acq.get(key, {})
        active    = info.get('active', False)
        age_s     = info.get('age_s')
        running   = proc_running.get(proc_label, False)

        prefix = f'  {label}: '
        p(r, 0, prefix, BOLD)

        if active:
            age_str = f'last file {age_s}s ago' if age_s is not None else ''
            p(r, len(prefix), f'● ACTIVE   {age_str}', GREEN | BOLD)
        elif running:
            age_str = f'last file {age_s}s ago' if age_s is not None else 'no recent file'
            p(r, len(prefix), f'● INACTIVE   {age_str}', RED | BOLD)
        else:
            p(r, len(prefix), '● STOPPED', YELLOW | BOLD)
        r += 1

    # ── Buzzer schedule ──────────────────────────────────────────────────────
    p(r, 0, '  BUZZER SCHEDULE', BOLD); r += 1
    hr(r); r += 1

    bz = data.get('buzzer', {})
    if not bz.get('enabled', False):
        p(r, 0, '  Status: ', BOLD)
        p(r, 10, 'DISABLED', YELLOW | BOLD)
        r += 1
    else:
        p(r, 0, '  Status: ', BOLD)
        p(r, 10, 'ENABLED', GREEN | BOLD)
        r += 1

        next_local  = bz.get('next_local')
        next_utc    = bz.get('next_utc')
        next_in_min = bz.get('next_in_min')
        last_local  = bz.get('last_local')
        last_utc    = bz.get('last_utc')

        if next_local is not None:
            in_min_str = f'in {next_in_min:.1f} min' if next_in_min is not None else ''
            next_str   = f'  Next  : {next_local} local'
            if next_utc:
                next_str += f' = {next_utc} UTC'
            if in_min_str:
                next_str += f'  ({in_min_str})'
            next_attr = GREEN if (next_in_min is not None and next_in_min > 5) else YELLOW
            p(r, 0, next_str, next_attr | BOLD)
        r += 1

        if last_local is not None:
            last_str = f'  Last  : {last_local} local'
            if last_utc:
                last_str += f' = {last_utc} UTC'
            p(r, 0, last_str)
        r += 1

    # ── Log activity ─────────────────────────────────────────────────────────
    p(r, 0, '  RECENT LOG ACTIVITY', BOLD); r += 1
    hr(r); r += 1

    LOG_LABELS = {
        'video':         'video        ',
        'imu':           'imu          ',
        'buzzer':        'buzzer       ',
        'power_manager': 'power_manager',
        'network':       'network      ',
        'voltage':       'voltage      ',
    }
    for lg in data['logs']:
        label = LOG_LABELS[lg['name']]
        prefix = f'  {label}: '
        p(r, 0, prefix, BOLD)

        if not lg['exists']:
            p(r, len(prefix), '(no log file yet)', YELLOW)
        elif lg['last_line'] is None:
            p(r, len(prefix), '(empty)', YELLOW)
        else:
            badge   = f' [{lg["err_1h"]} err/1h]' if lg['err_1h'] > 0 else ''
            max_len = W - len(prefix) - len(badge) - 1
            line    = lg['last_line']
            if len(line) > max_len:
                line = '…' + line[-(max_len - 1):]
            attr = RED if lg['is_error'] else 0
            p(r, len(prefix), line, attr)
            if badge:
                p(r, W - len(badge) - 1, badge, RED | BOLD)
        r += 1

    # ── Hardware & System ────────────────────────────────────────────────────
    p(r, 0, '  HARDWARE & SYSTEM', BOLD); r += 1
    hr(r); r += 1

    cam_ok, cam_detail = data['camera']
    cam_sym  = '✓' if cam_ok else ('?' if cam_ok is None else '✗')
    cam_attr = GREEN if cam_ok else (YELLOW if cam_ok is None else RED)

    imu_ok, imu_detail = data['imu_bus']
    imu_sym  = '✓' if imu_ok else ('?' if imu_ok is None else '✗')
    imu_attr = GREEN if imu_ok else (YELLOW if imu_ok is None else RED)

    cam_str = f'  Camera: {cam_sym} {cam_detail}'
    imu_str = f'I2C/IMU: {imu_sym} {imu_detail}'
    p(r, 0,        cam_str, cam_attr)
    p(r, max(len(cam_str) + 4, 32), imu_str, imu_attr)
    r += 1

    v      = data['voltage']
    low_v  = data['voltage_low_v']
    rec_v  = data['voltage_rec_v']
    if v is not None:
        v_str = f'  Voltage: {v:.1f} V'
        if low_v > 0 and v < low_v:
            v_attr = RED | BOLD
        elif rec_v > 0 and v < rec_v:
            v_attr = YELLOW | BOLD
        else:
            v_attr = GREEN
    else:
        v_str  = '  Voltage: n/a'
        v_attr = YELLOW
    thresh_str = f'(cutoff {low_v} V / recovery {rec_v} V)' if low_v > 0 else '(protection disabled)'
    p(r, 0, v_str, v_attr)
    p(r, max(len(v_str) + 2, 22), thresh_str)
    r += 1

    temp = data['cpu_temp']
    freq = data['cpu_freq']
    temp_str = f'  CPU: {temp:.1f}°C' if temp is not None else '  CPU: n/a'
    freq_str = f'{freq} MHz' if freq is not None else ''
    up_str   = f'Uptime: {data["uptime"]}'
    temp_attr = RED if (temp is not None and temp > 80) else \
                YELLOW if (temp is not None and temp > 70) else GREEN
    p(r, 0,  temp_str, temp_attr | BOLD)
    p(r, max(len(temp_str) + 2, 20), freq_str)
    p(r, max(len(temp_str) + len(freq_str) + 6, 34), up_str)
    r += 1

    st = data['storage']
    wifi_str = f'  WiFi: {data["wifi"]}'
    if st['total_gb'] is not None:
        disk_str = f'Disk: {st["used_gb"]:.1f}/{st["total_gb"]:.0f} GB ({st["pct"]:.0f}%)'
        disk_attr = RED if st['pct'] > 90 else (YELLOW if st['pct'] > 75 else GREEN)
    else:
        disk_str = 'Disk: unavailable'
        disk_attr = YELLOW
    vid_str = f'Video: {st["video_count"]} files' if st['video_count'] is not None else ''

    p(r, 0, wifi_str)
    p(r, max(len(wifi_str) + 2, 30), disk_str, disk_attr)
    p(r, max(len(wifi_str) + len(disk_str) + 6, 56), vid_str)
    r += 1

    # ── Footer ───────────────────────────────────────────────────────────────
    p(r, 0, '═' * W, BOLD); r += 1
    p(r, 0, f'  Refreshing in {secs_to_refresh}s', CYAN)

    stdscr.refresh()


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_monitor(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN,  -1)
    curses.init_pair(2, curses.COLOR_RED,    -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN,   -1)
    C = {
        'green':  curses.color_pair(1),
        'red':    curses.color_pair(2),
        'yellow': curses.color_pair(3),
        'cyan':   curses.color_pair(4),
    }

    script_dir  = Path(__file__).parent
    fishcam_id  = config.get_fishcam_id()
    paths       = config.get_paths()
    imu_cfg     = config.get_imu_settings()
    wittypi_cfg = config.get_wittypi_settings()
    buzzer_cfg  = config.get_buzzer_settings()

    last_refresh = 0.0
    data = None

    while True:
        now = time.monotonic()
        key = stdscr.getch()

        if key in (ord('q'), ord('Q'), 27):
            break

        force = key in (ord('r'), ord('R'))
        if force or (now - last_refresh) >= REFRESH_INTERVAL:
            data = collect(script_dir, fishcam_id, paths, imu_cfg, wittypi_cfg, buzzer_cfg)
            last_refresh = time.monotonic()

        if data:
            secs_left = max(0, REFRESH_INTERVAL - int(time.monotonic() - last_refresh))
            render(stdscr, data, secs_left, C)

        time.sleep(0.25)


def main():
    try:
        config.get_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    try:
        curses.wrapper(run_monitor)
    except KeyboardInterrupt:
        pass

    print("Monitor stopped.")


if __name__ == '__main__':
    main()
