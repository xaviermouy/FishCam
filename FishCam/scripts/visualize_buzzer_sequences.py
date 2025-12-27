"""
Visualize Buzzer Sequences for Multiple FishCams

This script reads the fishcam configuration and generates a time series visualization
showing when each fishcam's buzzer sequences occur. Useful for verifying that
sequences don't overlap when multiple fishcams start simultaneously.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import config
import argparse
import buzzer_utils


def calculate_sequence_timings(fishcam_num, buzzer_config, num_sequences=10):
    """
    Calculate beep timings for a single fishcam

    Args:
        fishcam_num: FishCam number (1-N)
        buzzer_config: Buzzer configuration dict
        num_sequences: Number of sequences to simulate

    Returns:
        tuple: (beeps, beep_number, gap_between_sequences, initial_delay)
            - beeps: List of (start_time, end_time) tuples for each beep
            - beep_number: Number of beeps per sequence
            - gap_between_sequences: Gap between sequences in seconds
            - initial_delay: Initial delay before first sequence (for sequential mode)
    """
    # Use shared utility function to calculate parameters
    beep_number, gap_between_sequences = buzzer_utils.calculate_buzzer_parameters(
        buzzer_config, fishcam_number=fishcam_num
    )

    # Calculate initial delay for sequential beeping
    initial_delay = buzzer_utils.calculate_initial_delay(
        buzzer_config, fishcam_number=fishcam_num
    )

    beep_dur = buzzer_config['beep_duration_sec']
    beep_gap = buzzer_config['beep_gap_sec']

    # Calculate all beep times (starting from initial_delay)
    beeps = []
    current_time = initial_delay

    for seq in range(num_sequences):
        # Each sequence starts at current_time
        for beep in range(beep_number):
            start = current_time + beep * (beep_dur + beep_gap)
            end = start + beep_dur
            beeps.append((start, end))

        # Calculate when next sequence starts
        sequence_duration = buzzer_utils.calculate_sequence_duration(
            beep_number, beep_dur, beep_gap
        )
        current_time += sequence_duration + gap_between_sequences

    return beeps, beep_number, gap_between_sequences, initial_delay


def visualize_sequences(buzzer_config, duration=None):
    """
    Create a visualization of buzzer sequences for all fishcams

    Args:
        buzzer_config: Buzzer configuration dict (all parameters from config)
        duration: Time duration to show (seconds), None = auto
    """
    mode = buzzer_config.get('mode', 'manual')

    # Get parameters from config
    num_sequences = buzzer_config.get('number_sequences', 5)

    if mode == 'auto':
        total_fishcams = buzzer_config['auto']['total_fishcams']
    else:
        # In manual mode, we can't determine number of fishcams from config
        # Default to 1 (single fishcam visualization)
        total_fishcams = 1

    # Calculate timings for each fishcam
    all_fishcam_data = []
    max_time = 0

    for fishcam_num in range(1, total_fishcams + 1):
        beeps, beep_number, gap, initial_delay = calculate_sequence_timings(fishcam_num, buzzer_config, num_sequences)
        all_fishcam_data.append({
            'fishcam_num': fishcam_num,
            'beeps': beeps,
            'beep_number': beep_number,
            'gap': gap,
            'initial_delay': initial_delay
        })
        if beeps:
            max_time = max(max_time, beeps[-1][1])

    if duration is None:
        duration = max_time

    # Create the plot
    fig, ax = plt.subplots(figsize=(14, 8))

    # Colors for different fishcams
    colors = plt.cm.tab10(np.linspace(0, 1, total_fishcams))

    # Plot each fishcam's beeps
    for idx, fishcam_data in enumerate(all_fishcam_data):
        fishcam_num = fishcam_data['fishcam_num']
        beeps = fishcam_data['beeps']
        beep_number = fishcam_data['beep_number']

        # Plot each beep as a horizontal bar
        for start, end in beeps:
            if start <= duration:
                ax.barh(fishcam_num, end - start, left=start, height=0.6,
                       color=colors[idx], alpha=0.8, edgecolor='black', linewidth=0.5)

        # Add label showing beep count
        ax.text(duration * 1.02, fishcam_num, f'{beep_number} beeps',
               va='center', fontsize=9)

    # Formatting
    ax.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_ylabel('FishCam Number', fontsize=12, fontweight='bold')

    # Update title based on mode
    if mode == 'auto':
        title = 'Buzzer Sequence Timeline for All FishCams\n(Sequential beeping - one after another)'
    else:
        title = 'Buzzer Sequence Timeline for All FishCams\n(Manual mode)'

    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

    ax.set_ylim(0.5, total_fishcams + 0.5)
    ax.set_xlim(0, duration * 1.15)
    ax.set_yticks(range(1, total_fishcams + 1))
    ax.grid(True, axis='x', alpha=0.3, linestyle='--')

    # Add mode and parameters info
    mode_text = f"Mode: {mode.upper()}"
    if mode == 'auto':
        params_text = (f"Base beeps: {buzzer_config['auto']['base_beeps']}, "
                      f"Beep duration: {buzzer_config['beep_duration_sec']}s, "
                      f"Beep gap: {buzzer_config['beep_gap_sec']}s, "
                      f"Safety buffer: {buzzer_config['auto'].get('safety_buffer', 1.5)}x")
    else:
        params_text = (f"Beeps: {buzzer_config['manual']['beep_number']}, "
                      f"Gap: {buzzer_config['manual']['gap_between_sequences_sec']}s")

    fig.text(0.5, 0.02, f"{mode_text} | {params_text}",
            ha='center', fontsize=10, style='italic', color='gray')

    # Add legend for sequences
    legend_elements = [
        mpatches.Patch(facecolor='gray', alpha=0.8, edgecolor='black',
                      label='Individual beep')
    ]
    ax.legend(handles=legend_elements, loc='upper right')

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    return fig, ax


def main():
    parser = argparse.ArgumentParser(
        description='Visualize FishCam buzzer sequences using configuration from fishcam_config.yaml'
    )
    parser.add_argument('--config', type=str, default='fishcam_config.yaml',
                       help='Path to configuration file (default: fishcam_config.yaml)')
    parser.add_argument('--duration', type=float, default=None,
                       help='Duration to visualize in seconds (auto if not specified)')
    parser.add_argument('--output', type=str, default=None,
                       help='Save figure to file (e.g., buzzer_timeline.png)')

    args = parser.parse_args()

    # Load configuration
    print(f"Loading configuration from {args.config}...")
    cfg = config.get_config(args.config)
    buzzer_config = cfg.get_buzzer_settings()

    # Display configuration info
    mode = buzzer_config.get('mode', 'manual')
    num_sequences = buzzer_config.get('number_sequences', 5)

    if mode == 'auto':
        total_fishcams = buzzer_config['auto']['total_fishcams']
        print(f"Mode: AUTO")
        print(f"Total fishcams: {total_fishcams}")
        print(f"Base beeps: {buzzer_config['auto']['base_beeps']}")
        print(f"Safety buffer: {buzzer_config['auto'].get('safety_buffer_sec', 0.5)}s")
    else:
        total_fishcams = 1
        print(f"Mode: MANUAL")
        print(f"Beep number: {buzzer_config['manual']['beep_number']}")
        print(f"Gap: {buzzer_config['manual']['gap_between_sequences_sec']}s")

    print(f"Sequences per fishcam: {num_sequences}")
    print(f"Beep duration: {buzzer_config['beep_duration_sec']}s")
    print(f"Beep gap: {buzzer_config['beep_gap_sec']}s")

    # Create visualization
    print(f"\nGenerating visualization...")
    fig, ax = visualize_sequences(buzzer_config, duration=args.duration)

    # Save or show
    if args.output:
        print(f"Saving figure to {args.output}...")
        plt.savefig(args.output, dpi=300, bbox_inches='tight')
        print("Done!")
    else:
        print("Displaying figure...")
        plt.show()


if __name__ == '__main__':
    main()
