import lgpio
import time
import config
import logging
from datetime import datetime
import os
import sys
import buzzer_utils

# Get log directory from config
paths = config.get_paths()
logDir = paths['log_dir']

# Create log directory if it doesn't exist
if not os.path.isdir(logDir):
    os.makedirs(logDir)

# Get log filename from command line argument if provided, otherwise create new one
if len(sys.argv) > 1:
    log_filename = sys.argv[1]
else:
    log_filename = os.path.join(logDir, f"buzzer_{time.strftime('%Y%m%dT%H%M%S')}.log")

# Configure logging to file (same format as captureVideo.py)
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)

def playBeepSequence(chip, buzzer_pin, beep_dur_sec, beep_gap_sec, beep_number):
    """Play a sequence of beeps"""
    for n in range(0, beep_number):
        # Turn buzzer ON for the time period defined
        lgpio.gpio_write(chip, buzzer_pin, 1)  # turn ON
        time.sleep(beep_dur_sec)  # duration of each beep
        lgpio.gpio_write(chip, buzzer_pin, 0)  # turn OFF
        time.sleep(beep_gap_sec)  # duration between beeps (silence)

# Load configuration
buzzer_config = config.get_buzzer_settings()
fishcam_config = config.get_fishcam_settings()

# Get common settings
buzzer_pin = buzzer_config['pin']
beep_dur_sec = buzzer_config['beep_duration_sec']
beep_gap_sec = buzzer_config['beep_gap_sec']
number_beep_sequences = buzzer_config['number_sequences']
mode = buzzer_config.get('mode', 'manual')

# Calculate beep_number and gap using shared utility functions
beep_number, gap_btw_sequences_sec = buzzer_utils.calculate_buzzer_parameters(
    buzzer_config, fishcam_config
)

# Print configuration info
if mode == 'auto':
    fishcam_number = buzzer_utils.extract_fishcam_number(fishcam_config['id'])
    base_beeps = buzzer_config['auto']['base_beeps']
    safety_buffer_sec = buzzer_config['auto'].get('safety_buffer_sec', 0.5)

    print(f"Auto mode: FishCam #{fishcam_number}")
    print(f"Beeps per sequence: {beep_number} ({base_beeps} base + {fishcam_number})")
    print(f"Gap between sequences: {gap_btw_sequences_sec:.2f}s (includes {safety_buffer_sec:.2f}s safety buffer per fishcam)")
else:
    print(f"Manual mode: {beep_number} beeps per sequence")

# Calculate and apply initial delay for sequential beeping (auto mode only)
initial_delay = buzzer_utils.calculate_initial_delay(buzzer_config, fishcam_config)
if initial_delay > 0:
    print(f"Waiting {initial_delay:.2f}s before starting (sequential mode)...")
    logging.info(f"Initial delay: {initial_delay:.2f}s for sequential beeping")
    time.sleep(initial_delay)

# Open the GPIO chip (0 for /dev/gpiochip0)
chip = lgpio.gpiochip_open(0)

# Set the buzzer pin as output
lgpio.gpio_claim_output(chip, buzzer_pin)

# Play beep sequences
for seq in range(0, number_beep_sequences):
    sequence_start_time = datetime.now()
    logging.info(
        f"Buzzer sequence {seq + 1}/{number_beep_sequences} starting at {sequence_start_time.strftime('%H:%M:%S.%f')[:-3]} "
        f"| Beeps: {beep_number} | Beep duration: {beep_dur_sec}s | Gap between beeps: {beep_gap_sec}s"
    )
    playBeepSequence(chip, buzzer_pin, beep_dur_sec, beep_gap_sec, beep_number)
    time.sleep(gap_btw_sequences_sec)

# Clean up and close the GPIO chip
lgpio.gpio_write(chip, buzzer_pin, 0)  # Ensure buzzer is OFF
lgpio.gpiochip_close(chip)