import RPi.GPIO as GPIO
import time

# input parameters
buzzer_pin = 26
beep_dur_sec = 0.01
beep_gap_sec = 0.5
beep_number = 10
number_beep_sequences = 5
gap_btw_sequences_sec = 5

def playBeepSequence(buzzer_pin,beep_dur_sec,beep_gap_sec,beep_number):
    for n in range(0,beep_number):
        # Turn buzzer ON for the time period defined
        GPIO.output(buzzer_pin, True) # turn ON
        time.sleep(beep_dur_sec) # duration of each beep
        GPIO.output(buzzer_pin, False)# turn OFF
        time.sleep(beep_gap_sec) # dution between beeps (silence)

# Setting up GPIO
GPIO.setwarnings(False) 
GPIO.setmode(GPIO.BCM) # Broadcom chip-specific pin numbers.(different than the Board numbering scheme)
GPIO.setup(buzzer_pin, GPIO.OUT) # defines the buzzer pin as an "output" pin

# Play beep sequences
for seq in range(0,number_beep_sequences):
    playBeepSequence(buzzer_pin,beep_dur_sec,beep_gap_sec,beep_number)
    time.sleep(gap_btw_sequences_sec) 

# Close all open ports
GPIO.cleanup()