#!/usr/bin/env python3
"""
Parser for wittyPi log files.
Extracts voltage readings (Vin and Vout) with timestamps and saves to CSV and plot.

Usage examples:
    # Basic usage - parse log and save to output folder
    python parse_wittypi_log.py /path/to/wittyPi.log /path/to/output

    # Display the plot interactively (in addition to saving)
    python parse_wittypi_log.py /path/to/wittyPi.log /path/to/output --show

Output files created in output folder:
    - wittypi_voltages.csv: Voltage readings with timestamps
    - wittypi_voltages.png: Plot of Vin and Vout over time

Requirements:
    - matplotlib (for plotting): pip install matplotlib
"""

import re
import argparse
from pathlib import Path
from datetime import datetime
import csv


def parse_wittypi_log(log_file_path):
    """
    Parse wittyPi log file and extract timestamp, Vin, and Vout values.

    Args:
        log_file_path (str): Path to the wittyPi log file

    Returns:
        list: List of dictionaries with 'datetime', 'vin', 'vout' keys
    """
    data = []

    # Regex patterns for timestamp and voltage values
    # Matches both [timestamp] and <timestamp> formats
    timestamp_pattern = r'[\[<](\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\]>]'
    # Pattern for lines with both Vin and Vout
    vin_vout_pattern = r'Current Vin=([\d.]+)V, Vout=([\d.]+)V'
    # Pattern for lines with only Vout
    vout_only_pattern = r'Current Vout=([\d.]+)V'

    with open(log_file_path, 'r') as f:
        for line in f:
            # Check if line contains "Current" voltage information
            if 'Current' not in line:
                continue

            # Extract timestamp
            timestamp_match = re.search(timestamp_pattern, line)
            if not timestamp_match:
                continue

            timestamp_str = timestamp_match.group(1)
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

            # Try to extract both Vin and Vout
            vin_vout_match = re.search(vin_vout_pattern, line)
            if vin_vout_match:
                vin = float(vin_vout_match.group(1))
                vout = float(vin_vout_match.group(2))
                data.append({
                    'datetime': dt,
                    'vin': vin,
                    'vout': vout
                })
            else:
                # Try to extract only Vout
                vout_match = re.search(vout_only_pattern, line)
                if vout_match:
                    vout = float(vout_match.group(1))
                    data.append({
                        'datetime': dt,
                        'vin': None,
                        'vout': vout
                    })

    return data


def save_to_csv(data, output_file):
    """
    Save parsed data to CSV file.

    Args:
        data (list): List of dictionaries with voltage data
        output_file (str): Path to output CSV file
    """
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['datetime', 'vin', 'vout']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in data:
            writer.writerow({
                'datetime': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                'vin': row['vin'] if row['vin'] is not None else '',
                'vout': row['vout']
            })

    print(f"Data saved to {output_file}")


def plot_voltages(data, output_file):
    """
    Create a plot of Vin and Vout over time and save to file.

    Args:
        data (list): List of dictionaries with voltage data
        output_file (str): Path to save the plot
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("Error: matplotlib is required for plotting. Install it with: pip install matplotlib")
        return

    # Separate data into lists for plotting
    datetimes = [row['datetime'] for row in data]
    vins = [row['vin'] for row in data if row['vin'] is not None]
    vouts = [row['vout'] for row in data]
    datetimes_with_vin = [row['datetime'] for row in data if row['vin'] is not None]

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot Vout (all data points)
    ax.plot(datetimes, vouts, 'b-', label='Vout', linewidth=2, marker='o', markersize=3)

    # Plot Vin (only where available)
    if vins:
        ax.plot(datetimes_with_vin, vins, 'r-', label='Vin', linewidth=2, marker='s', markersize=3)

    # Format the plot
    ax.set_xlabel('Datetime', fontsize=12)
    ax.set_ylabel('Voltage (V)', fontsize=12)
    ax.set_title('WittyPi Voltage Readings Over Time', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()

    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to {output_file}")


def main():
    """Main function to parse arguments and run the parser."""
    parser = argparse.ArgumentParser(
        description='Parse wittyPi log file and extract voltage readings.'
    )
    parser.add_argument(
        'log_file',
        type=str,
        help='Path to the wittyPi log file'
    )
    parser.add_argument(
        'output_folder',
        type=str,
        help='Path to the output folder for results'
    )
    parser.add_argument(
        '--show',
        action='store_true',
        help='Display the plot interactively (in addition to saving)'
    )

    args = parser.parse_args()

    # Check if log file exists
    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"Error: Log file '{args.log_file}' not found.")
        return

    # Create output folder if it doesn't exist
    output_path = Path(args.output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Define output file paths
    csv_output = output_path / 'wittypi_voltages.csv'
    plot_output = output_path / 'wittypi_voltages.png'

    # Parse the log file
    print(f"Parsing log file: {args.log_file}")
    data = parse_wittypi_log(args.log_file)

    if not data:
        print("No voltage data found in the log file.")
        return

    print(f"Found {len(data)} voltage readings")

    # Count entries with Vin
    vin_count = sum(1 for row in data if row['vin'] is not None)
    print(f"  - {vin_count} entries with Vin")
    print(f"  - {len(data)} entries with Vout")

    # Save to CSV
    save_to_csv(data, csv_output)

    # Create and save plot
    plot_voltages(data, plot_output)

    # Show plot if requested
    if args.show:
        try:
            import matplotlib.pyplot as plt
            plt.show()
        except ImportError:
            print("Warning: matplotlib not available for displaying plot.")


if __name__ == '__main__':
    main()
