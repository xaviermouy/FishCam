#!/usr/bin/env python3
"""
Parser for FishCam camera log files.
Extracts frame statistics, buzzer sequences, and log messages from log files.

Usage examples:
    # Basic usage - parse logs and save to output folder
    python parse_camera_logs.py /path/to/logs /path/to/output

    # Example with actual paths
    python parse_camera_logs.py K:/FishCam02/Desktop/FishCam/FishCam/logs ./output

Output files created in output folder:
    - frame_stats.csv: Frame statistics for all log files
    - dropped_frames.png: Plot of dropped frames over time
    - buzzer_sequences.csv: Buzzer sequence information
    - warning_messages.csv: All WARNING log messages (if any)
    - error_messages.csv: All ERROR log messages (if any)

Requirements:
    - matplotlib (for plotting): pip install matplotlib
"""

import re
import argparse
from pathlib import Path
from datetime import datetime
import csv


def extract_datetime_from_filename(filename):
    """
    Extract datetime from log filename.

    Args:
        filename (str): Log filename (e.g., '20260105T125138.log')

    Returns:
        datetime: Parsed datetime object, or None if parsing fails
    """
    # Pattern: YYYYMMDDTHHMMSS.log
    pattern = r'(\d{8})T(\d{6})\.log'
    match = re.match(pattern, filename)

    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        try:
            dt = datetime.strptime(date_str + time_str, '%Y%m%d%H%M%S')
            return dt
        except ValueError:
            return None
    return None


def extract_datetime_from_metadata_filename(filename):
    """
    Extract datetime from metadata filename.

    Args:
        filename (str): Metadata filename (e.g., '8_fishcam02_20260105T125139.610033Z_..._metadata.json')

    Returns:
        datetime: Parsed datetime object, or None if parsing fails
    """
    # Pattern: YYYYMMDDTHHMMSS.microsecondsZ
    pattern = r'(\d{8})T(\d{6})\.(\d+)Z'
    match = re.search(pattern, filename)

    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        microsec_str = match.group(3)  # microseconds
        try:
            # Parse the base datetime
            dt = datetime.strptime(date_str + time_str, '%Y%m%d%H%M%S')
            # Add microseconds
            microseconds = int(microsec_str)
            dt = dt.replace(microsecond=microseconds)
            return dt
        except ValueError:
            return None
    return None


def parse_frame_stats(log_file_path):
    """
    Parse frame statistics from a log file.

    Args:
        log_file_path (Path): Path to the log file

    Returns:
        list: List of dictionaries with frame stats
    """
    results = []
    log_filename = log_file_path.name
    file_datetime = extract_datetime_from_filename(log_filename)

    if file_datetime is None:
        return results

    # Pattern for frame stats: Expected=9000, Actual=8860, Dropped=140
    frame_pattern = r'Frame stats:\s*Expected=(\d+),\s*Actual=(\d+),\s*Dropped=(\d+)'
    # Pattern for metadata filename
    metadata_pattern = r'Frame metadata saved:\s*(.+\.json)'

    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()

        # Iterate through lines and look for frame stats
        for i, line in enumerate(lines):
            match = re.search(frame_pattern, line)
            if match:
                expected = int(match.group(1))
                actual = int(match.group(2))
                dropped = int(match.group(3))

                # Look for metadata filename in previous line
                metadata_filename = None
                entry_datetime = file_datetime  # Default to log file datetime

                if i > 0:
                    metadata_match = re.search(metadata_pattern, lines[i-1])
                    if metadata_match:
                        # Extract just the filename from the path
                        full_path = metadata_match.group(1)
                        metadata_filename = Path(full_path).name

                        # Extract datetime from metadata filename
                        metadata_datetime = extract_datetime_from_metadata_filename(metadata_filename)
                        if metadata_datetime:
                            entry_datetime = metadata_datetime

                # Use metadata filename if found, otherwise use log filename
                filename = metadata_filename if metadata_filename else log_filename

                results.append({
                    'datetime': entry_datetime,
                    'filename': filename,
                    'expected': expected,
                    'actual': actual,
                    'dropped': dropped
                })
    except Exception as e:
        print(f"Warning: Error reading {log_file_path}: {e}")

    return results


def parse_buzzer_sequences(log_file_path):
    """
    Parse buzzer sequences from a buzzer log file.

    Matches log lines written by run_buzzer.py:
      - Config at startup: "Beeps per sequence     : 14"
      - Per-sequence:      "Sequence 1/5 at 08:00:00.678"

    Args:
        log_file_path (Path): Path to the log file

    Returns:
        list: List of dictionaries with buzzer sequence data
    """
    results = []
    filename = log_file_path.name

    # Pattern for the per-sequence line logged by run_buzzer.py
    # Example: "2026-07-30 08:00:00,678 INFO Sequence 1/5 at 08:00:00.678"
    seq_pattern      = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+Sequence\s+(\d+/\d+)\s+at\s+([\d:\.]+)'

    # msequence mode startup patterns
    seq_mode_pattern = r'INFO\s+Sequence mode\s+:\s+(\w+)'
    mseq_n_pattern   = r'INFO\s+M-sequence n\s+:\s+(\d+)'
    chip_dur_pattern = r'INFO\s+Chip duration\s+:\s+([\d.]+)'
    seq_len_pattern  = r'INFO\s+Sequence length\s+:\s+(\d+)\s+chips'
    unit_num_pattern = r'INFO\s+Unit number\s+:\s+(\d+)'
    seq_pat_pattern  = r'INFO\s+Sequence pattern\s+:\s+([\d,]+)'

    # beep (legacy) mode startup patterns
    beep_cnt_pattern = r'INFO\s+Beeps per sequence\s+:\s+(\d+)'
    beep_dur_pattern = r'INFO\s+Beep duration\s+:\s+([\d.]+)'
    beep_gap_pattern = r'INFO\s+Gap between beeps\s+:\s+([\d.]+)'

    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()

        # Startup config values — updated on each new session start in the log
        seq_mode   = 'beep'   # default for old logs without sequence_mode line
        mseq_n     = None
        chip_dur   = None
        seq_len    = None
        unit_num   = None
        seq_pattern_str = None
        beep_count = None
        beep_dur   = None
        beep_gap   = None

        for line in lines:
            m = re.search(seq_mode_pattern, line)
            if m:
                seq_mode = m.group(1)
            m = re.search(mseq_n_pattern, line)
            if m:
                mseq_n = int(m.group(1))
            m = re.search(chip_dur_pattern, line)
            if m:
                chip_dur = float(m.group(1))
            m = re.search(seq_len_pattern, line)
            if m:
                seq_len = int(m.group(1))
            m = re.search(unit_num_pattern, line)
            if m:
                unit_num = int(m.group(1))
            m = re.search(seq_pat_pattern, line)
            if m:
                seq_pattern_str = m.group(1)
            m = re.search(beep_cnt_pattern, line)
            if m:
                beep_count = int(m.group(1))
            m = re.search(beep_dur_pattern, line)
            if m:
                beep_dur = float(m.group(1))
            m = re.search(beep_gap_pattern, line)
            if m:
                beep_gap = float(m.group(1))

            # Match per-sequence timestamp lines
            m = re.search(seq_pattern, line)
            if m:
                date_str = m.group(1)   # YYYY-MM-DD HH:MM:SS
                sequence = m.group(2)   # e.g. "1/5"
                time_str = m.group(3)   # HH:MM:SS.mmm

                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    time_parts = time_str.split(':')
                    hours   = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = float(time_parts[2])
                    dt = dt.replace(
                        hour=hours, minute=minutes,
                        second=int(seconds),
                        microsecond=int((seconds % 1) * 1_000_000)
                    )
                    results.append({
                        'datetime':         dt,
                        'sequence':         sequence,
                        'sequence_mode':    seq_mode,
                        # msequence fields
                        'msequence_n':      mseq_n,
                        'chip_duration':    chip_dur,
                        'sequence_length':  seq_len,
                        'unit_number':      unit_num,
                        'sequence_pattern': seq_pattern_str,
                        # beep (legacy) fields
                        'beeps':            beep_count,
                        'beep_duration':    beep_dur,
                        'gap_between_beeps': beep_gap,
                    })
                except (ValueError, IndexError) as e:
                    print(f"Warning: Could not parse buzzer line in {filename}: {e}")

    except OSError as e:
        print(f"Warning: Could not read {log_file_path}: {e}")

    return results


def parse_log_messages(log_file_path, level):
    """
    Parse WARNING or ERROR messages from a log file.

    Args:
        log_file_path (Path): Path to the log file
        level (str): Log level to extract ('WARNING' or 'ERROR')

    Returns:
        list: List of dictionaries with log message data
    """
    results = []
    log_filename = log_file_path.name

    # Pattern: YYYY-MM-DD HH:MM:SS,milliseconds LEVEL message
    # Example: 2026-01-05 12:51:38,782 WARNING Frame loss detected
    log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d+)\s+' + level + r'\s+(.+)'
    # Pattern for metadata filename
    metadata_pattern = r'Frame metadata saved:\s*(.+\.json)'

    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()

        # Iterate through lines and look for WARNING/ERROR messages
        for i, line in enumerate(lines):
            match = re.search(log_pattern, line)
            if match:
                datetime_str = match.group(1)  # YYYY-MM-DD HH:MM:SS
                milliseconds = match.group(2)  # milliseconds
                message      = match.group(3)  # message text

                # Look backwards for metadata filename (up to 10 lines back)
                metadata_filename = None
                for j in range(max(0, i - 10), i):
                    metadata_match = re.search(metadata_pattern, lines[j])
                    if metadata_match:
                        full_path = metadata_match.group(1)
                        metadata_filename = Path(full_path).name
                        break

                filename = metadata_filename if metadata_filename else log_filename

                try:
                    dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(microsecond=int(milliseconds) * 1000)

                    results.append({
                        'datetime': dt,
                        'filename': filename,
                        'level':    level,
                        'message':  message,
                    })
                except ValueError as e:
                    print(f"Warning: Could not parse datetime '{datetime_str}' in {log_filename}: {e}")
    except Exception as e:
        print(f"Warning: Error reading {log_file_path}: {e}")

    return results


def save_frame_stats_csv(data, output_file):
    """
    Save frame statistics to CSV file.

    Args:
        data (list): List of dictionaries with frame stats
        output_file (Path): Path to output CSV file
    """
    if not data:
        print("No frame statistics found.")
        return

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['datetime', 'filename', 'expected', 'actual', 'dropped']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in data:
            writer.writerow({
                'datetime': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                'filename': row['filename'],
                'expected': row['expected'],
                'actual': row['actual'],
                'dropped': row['dropped']
            })

    print(f"Frame statistics saved to {output_file}")


def save_buzzer_sequences_csv(data, output_file):
    """
    Save buzzer sequences to CSV file.

    Args:
        data (list): List of dictionaries with buzzer sequence data
        output_file (Path): Path to output CSV file
    """
    if not data:
        print("No buzzer sequences found.")
        return

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = [
            'datetime', 'sequence', 'sequence_mode',
            'msequence_n', 'chip_duration', 'sequence_length', 'unit_number',
            'beeps', 'beep_duration', 'gap_between_beeps',
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in data:
            writer.writerow({
                'datetime':        row['datetime'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'sequence':        row['sequence'],
                'sequence_mode':   row.get('sequence_mode', ''),
                'msequence_n':     row.get('msequence_n', ''),
                'chip_duration':   row.get('chip_duration', ''),
                'sequence_length': row.get('sequence_length', ''),
                'unit_number':     row.get('unit_number', ''),
                'beeps':           row.get('beeps', ''),
                'beep_duration':   row.get('beep_duration', ''),
                'gap_between_beeps': row.get('gap_between_beeps', ''),
            })

    print(f"Buzzer sequences saved to {output_file}")


def save_log_messages_csv(data, output_file, level):
    """
    Save log messages (WARNING or ERROR) to CSV file.

    Args:
        data (list): List of dictionaries with log message data
        output_file (Path): Path to output CSV file
        level (str): Log level ('WARNING' or 'ERROR')
    """
    if not data:
        print(f"No {level} messages found.")
        return

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['datetime', 'filename', 'level', 'message']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in data:
            writer.writerow({
                'datetime': row['datetime'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'filename': row['filename'],
                'level':    row['level'],
                'message':  row['message'],
            })

    print(f"{level} messages saved to {output_file}")


def plot_dropped_frames(data, output_file):
    """
    Create a plot of dropped frames over time.

    Args:
        data (list): List of dictionaries with frame stats
        output_file (Path): Path to save the plot
    """
    if not data:
        print("No frame statistics to plot.")
        return

    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("Error: matplotlib is required for plotting. Install it with: pip install matplotlib")
        return

    # Sort data by datetime
    sorted_data = sorted(data, key=lambda x: x['datetime'])

    # Extract data for plotting
    datetimes = [row['datetime'] for row in sorted_data]
    dropped = [row['dropped'] for row in sorted_data]

    # Create the plot
    fig, ax = plt.subplots(figsize=(14, 6))

    # Plot dropped frames
    ax.plot(datetimes, dropped, 'r-', linewidth=2, marker='o', markersize=4, label='Dropped Frames')

    # Format the plot
    ax.set_xlabel('Datetime', fontsize=12)
    ax.set_ylabel('Dropped Frames', fontsize=12)
    ax.set_title('Dropped Frames Over Time', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Dropped frames plot saved to {output_file}")
    plt.close()


def main():
    """Main function to parse arguments and run the parser."""
    parser = argparse.ArgumentParser(
        description='Parse FishCam camera log files and extract frame statistics and buzzer sequences.'
    )
    parser.add_argument(
        'input_folder',
        type=str,
        help='Path to the folder containing log files'
    )
    parser.add_argument(
        'output_folder',
        type=str,
        help='Path to the folder where output files will be saved'
    )

    args = parser.parse_args()

    # Validate input folder
    input_path = Path(args.input_folder)
    if not input_path.exists():
        print(f"Error: Input folder '{args.input_folder}' not found.")
        return

    if not input_path.is_dir():
        print(f"Error: '{args.input_folder}' is not a directory.")
        return

    # Create output folder if it doesn't exist
    output_path = Path(args.output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Collect all log files; route each type to the appropriate parser
    all_log_files    = sorted(input_path.glob('*.log'))
    video_log_files  = [f for f in all_log_files if f.name.startswith('video_')]
    buzzer_log_files = [f for f in all_log_files if f.name.startswith('buzzer_')]

    if not all_log_files:
        print(f"No log files found in '{args.input_folder}'.")
        return

    print(f"Found {len(all_log_files)} log file(s): "
          f"{len(video_log_files)} video, {len(buzzer_log_files)} buzzer, "
          f"{len(all_log_files)} total for warnings/errors.")

    # Parse all log files
    all_frame_stats      = []
    all_buzzer_sequences = []
    all_warning_messages = []
    all_error_messages   = []

    for log_file in video_log_files:
        all_frame_stats.extend(parse_frame_stats(log_file))

    for log_file in buzzer_log_files:
        all_buzzer_sequences.extend(parse_buzzer_sequences(log_file))

    for log_file in all_log_files:
        all_warning_messages.extend(parse_log_messages(log_file, 'WARNING'))
        all_error_messages.extend(parse_log_messages(log_file, 'ERROR'))

    print(f"\nExtracted {len(all_frame_stats)} frame statistics entries.")
    print(f"Extracted {len(all_buzzer_sequences)} buzzer sequence entries.")
    print(f"Extracted {len(all_warning_messages)} WARNING messages.")
    print(f"Extracted {len(all_error_messages)} ERROR messages.")

    # Save results
    if all_frame_stats:
        frame_stats_csv = output_path / 'frame_stats.csv'
        save_frame_stats_csv(all_frame_stats, frame_stats_csv)

        # Create plot
        dropped_frames_plot = output_path / 'dropped_frames.png'
        plot_dropped_frames(all_frame_stats, dropped_frames_plot)

    if all_buzzer_sequences:
        buzzer_csv = output_path / 'buzzer_sequences.csv'
        save_buzzer_sequences_csv(all_buzzer_sequences, buzzer_csv)

    if all_warning_messages:
        warning_csv = output_path / 'warning_messages.csv'
        save_log_messages_csv(all_warning_messages, warning_csv, 'WARNING')

    if all_error_messages:
        error_csv = output_path / 'error_messages.csv'
        save_log_messages_csv(all_error_messages, error_csv, 'ERROR')

    print("\nProcessing complete!")


if __name__ == '__main__':
    main()
