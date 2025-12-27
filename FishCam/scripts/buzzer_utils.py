"""
Buzzer Utilities Module

Shared functions for calculating buzzer sequence parameters.
Used by both runBuzzer.py and visualize_buzzer_sequences.py
to ensure consistency.
"""

import re


def extract_fishcam_number(fishcam_id):
    """
    Extract numeric ID from fishcam identifier

    Args:
        fishcam_id: String identifier (e.g., 'fishcam01', 'fishcam02')

    Returns:
        int: Numeric fishcam ID

    Raises:
        ValueError: If no number found in fishcam_id
    """
    match = re.search(r'\d+', fishcam_id)
    if match:
        return int(match.group())
    else:
        raise ValueError(f"Could not extract fishcam number from ID: {fishcam_id}")


def calculate_buzzer_parameters(buzzer_config, fishcam_config=None, fishcam_number=None):
    """
    Calculate buzzer parameters based on mode (auto or manual)

    Args:
        buzzer_config: Buzzer configuration dictionary
        fishcam_config: FishCam configuration dictionary (optional, for auto mode)
        fishcam_number: Fishcam number (optional, overrides fishcam_config)

    Returns:
        tuple: (beep_number, gap_between_sequences_sec)

    Example:
        >>> beep_number, gap = calculate_buzzer_parameters(buzzer_config, fishcam_config)
    """
    mode = buzzer_config.get('mode', 'manual')
    beep_dur_sec = buzzer_config['beep_duration_sec']
    beep_gap_sec = buzzer_config['beep_gap_sec']

    if mode == 'auto':
        # Extract fishcam number
        if fishcam_number is None:
            if fishcam_config is None:
                raise ValueError("Auto mode requires fishcam_config or fishcam_number")
            fishcam_number = extract_fishcam_number(fishcam_config['id'])

        # Get auto mode parameters
        base_beeps = buzzer_config['auto']['base_beeps']
        total_fishcams = buzzer_config['auto']['total_fishcams']
        safety_buffer_sec = buzzer_config['auto'].get('safety_buffer_sec', 0.5)

        # Calculate beep number: base + fishcam number
        beep_number = base_beeps + fishcam_number

        # Sequential beeping mode: fishcams beep one after another
        # Calculate the total time for one complete cycle of all fishcams
        # Cycle = sum(all sequence durations) + inter_fishcam_gaps + safety_buffers

        # Calculate total duration for all fishcams to beep sequentially
        total_cycle_duration = 0
        inter_fishcam_gap = beep_dur_sec + beep_gap_sec  # Small gap between fishcams

        for fc_num in range(1, total_fishcams + 1):
            fc_beeps = base_beeps + fc_num
            fc_duration = calculate_sequence_duration(fc_beeps, beep_dur_sec, beep_gap_sec)
            total_cycle_duration += fc_duration
            if fc_num < total_fishcams:  # Add gap between fishcams (except after last one)
                total_cycle_duration += inter_fishcam_gap

        # Add safety buffers for all fishcams to account for clock drift
        # Each fishcam gets safety_buffer_sec added to its delay, so total buffer = total_fishcams * safety_buffer_sec
        total_safety_buffer = total_fishcams * safety_buffer_sec

        # Gap between sequence iterations
        gap_between_sequences_sec = total_cycle_duration + total_safety_buffer

    else:  # manual mode
        beep_number = buzzer_config['manual']['beep_number']
        gap_between_sequences_sec = buzzer_config['manual']['gap_between_sequences_sec']

    return beep_number, gap_between_sequences_sec


def calculate_sequence_duration(beep_number, beep_duration_sec, beep_gap_sec):
    """
    Calculate the duration of a single beep sequence

    Args:
        beep_number: Number of beeps in the sequence
        beep_duration_sec: Duration of each beep in seconds
        beep_gap_sec: Gap between beeps in seconds

    Returns:
        float: Total duration of the sequence in seconds
    """
    return beep_number * beep_duration_sec + (beep_number - 1) * beep_gap_sec


def calculate_initial_delay(buzzer_config, fishcam_config=None, fishcam_number=None):
    """
    Calculate the initial delay before this fishcam starts beeping (for sequential mode)

    Args:
        buzzer_config: Buzzer configuration dictionary
        fishcam_config: FishCam configuration dictionary (optional)
        fishcam_number: Fishcam number (optional)

    Returns:
        float: Initial delay in seconds
    """
    mode = buzzer_config.get('mode', 'manual')

    if mode != 'auto':
        # Manual mode: use configured initial_delay_sec
        return buzzer_config.get('manual', {}).get('initial_delay_sec', 0)

    # Get fishcam number
    if fishcam_number is None:
        if fishcam_config is None:
            raise ValueError("Auto mode requires fishcam_config or fishcam_number")
        fishcam_number = extract_fishcam_number(fishcam_config['id'])

    # Fishcam 1 starts immediately
    if fishcam_number == 1:
        return 0

    # Calculate delay based on previous fishcams
    beep_dur_sec = buzzer_config['beep_duration_sec']
    beep_gap_sec = buzzer_config['beep_gap_sec']
    base_beeps = buzzer_config['auto']['base_beeps']
    safety_buffer_sec = buzzer_config['auto'].get('safety_buffer_sec', 0.5)
    inter_fishcam_gap = beep_dur_sec + beep_gap_sec

    delay = 0
    for fc_num in range(1, fishcam_number):
        fc_beeps = base_beeps + fc_num
        fc_duration = calculate_sequence_duration(fc_beeps, beep_dur_sec, beep_gap_sec)
        delay += fc_duration + inter_fishcam_gap + safety_buffer_sec

    return delay


def get_buzzer_info(buzzer_config, fishcam_config=None, fishcam_number=None):
    """
    Get complete buzzer information including timing details

    Args:
        buzzer_config: Buzzer configuration dictionary
        fishcam_config: FishCam configuration dictionary (optional)
        fishcam_number: Fishcam number (optional)

    Returns:
        dict: Dictionary with keys:
            - beep_number: Number of beeps per sequence
            - gap_between_sequences_sec: Gap between sequences
            - beep_duration_sec: Duration of each beep
            - beep_gap_sec: Gap between beeps
            - sequence_duration_sec: Total duration of one sequence
            - mode: 'auto' or 'manual'
            - fishcam_number: Fishcam number (if applicable)
    """
    mode = buzzer_config.get('mode', 'manual')
    beep_number, gap_between_sequences_sec = calculate_buzzer_parameters(
        buzzer_config, fishcam_config, fishcam_number
    )

    beep_duration_sec = buzzer_config['beep_duration_sec']
    beep_gap_sec = buzzer_config['beep_gap_sec']
    sequence_duration_sec = calculate_sequence_duration(beep_number, beep_duration_sec, beep_gap_sec)

    info = {
        'mode': mode,
        'beep_number': beep_number,
        'gap_between_sequences_sec': gap_between_sequences_sec,
        'beep_duration_sec': beep_duration_sec,
        'beep_gap_sec': beep_gap_sec,
        'sequence_duration_sec': sequence_duration_sec,
    }

    if fishcam_number is not None:
        info['fishcam_number'] = fishcam_number
    elif fishcam_config is not None and mode == 'auto':
        info['fishcam_number'] = extract_fishcam_number(fishcam_config['id'])

    return info
