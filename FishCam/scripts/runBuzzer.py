import lgpio
import time
import config

def playBeepSequence(chip, buzzer_pin, beep_dur_sec, beep_gap_sec, beep_number):
    """Play a sequence of beeps"""
    for n in range(0, beep_number):
        # Turn buzzer ON for the time period defined
        lgpio.gpio_write(chip, buzzer_pin, 1)  # turn ON
        time.sleep(beep_dur_sec)  # duration of each beep
        lgpio.gpio_write(chip, buzzer_pin, 0)  # turn OFF
        time.sleep(beep_gap_sec)  # duration between beeps (silence)

# Load buzzer configuration
buzzer_config = config.get_buzzer_settings()

buzzer_pin = buzzer_config['pin']
beep_dur_sec = buzzer_config['beep_duration_sec']
beep_gap_sec = buzzer_config['beep_gap_sec']
beep_number = buzzer_config['beep_number']
number_beep_sequences = buzzer_config['number_sequences']
gap_btw_sequences_sec = buzzer_config['gap_between_sequences_sec']

# Open the GPIO chip (0 for /dev/gpiochip0)
chip = lgpio.gpiochip_open(0)

# Set the buzzer pin as output
lgpio.gpio_claim_output(chip, buzzer_pin)

# Play beep sequences
for seq in range(0, number_beep_sequences):
    playBeepSequence(chip, buzzer_pin, beep_dur_sec, beep_gap_sec, beep_number)
    time.sleep(gap_btw_sequences_sec)

# Clean up and close the GPIO chip
lgpio.gpio_write(chip, buzzer_pin, 0)  # Ensure buzzer is OFF
lgpio.gpiochip_close(chip)