from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder, Quality
from picamera2.outputs import FileOutput
import time
from datetime import datetime
import os
import logging
import subprocess
import sys
import json
import config

# Global list to store frame metadata
frame_metadata = []
frame_counter = 0

def initVideoSettings():
    """Load video settings from configuration file"""
    return config.get_video_settings()

def capture_frame_metadata(request):
    """Callback to capture metadata for each encoded frame"""
    global frame_counter
    metadata = request.get_metadata()

    frame_info = {
        'frame_sequence': frame_counter,
        'sensor_timestamp_us': metadata.get('SensorTimestamp', -1),
        'system_time': time.time(),
        'datetime': datetime.now().astimezone().strftime('%Y%m%dT%H%M%S.%f%z'),
        'exposure_time': metadata.get('ExposureTime', -1),
        'analogue_gain': metadata.get('AnalogueGain', -1)
    }

    frame_metadata.append(frame_info)
    frame_counter += 1

def captureVideo(outDir, iterFileName, videoSettings, flagname=''):
    # Open iterator file for output filenames
    curDir = os.getcwd()
    iterFile = open(os.path.join(curDir, iterFileName), 'r')
    iterNumber = iterFile.read()
    if len(iterNumber) == 0:
        iterNumber = 1
    else:
        iterNumber = int(iterNumber)
    iterFile.close()

    # Get current time string for the file names
    now = datetime.now()
    timeStampStr = now.strftime("%Y%m%dT%H%M%S.%fZ")
    if len(flagname) > 0:
        flagname = '_' + flagname

    videofilename = os.path.join(
        outDir,
        str(iterNumber) + flagname + '_' + timeStampStr + '_' +
        str(videoSettings['resolution'][0]) + 'x' + str(videoSettings['resolution'][1]) +
        '_awbm-' + str(videoSettings['AwbMode']) +
        '_aem-' + str(videoSettings['AeExposureMode']) +
        '_fr-' + str(videoSettings['frameRate']) +
        '_q-' + str(videoSettings['quality']) +
        '_sh-' + str(videoSettings['sharpness']) +
        '_b-' + str(videoSettings['brightness']) +
        '_c-' + str(videoSettings['contrast']) +
        '_ag-' + str(videoSettings['AnalogueGain']) +
        '_sat-' + str(videoSettings['saturation']) +
        '.' + videoSettings['format']
    )
    print(videofilename)
    logging.info(videofilename)

    # Initialize camera
    camera = Picamera2()

    # Configure camera
    video_config = camera.create_video_configuration(
        main={"size": videoSettings['resolution'], "format": "RGB888"},
        controls={
            "FrameRate": videoSettings['frameRate']
        }
    )
    camera.configure(video_config)

    # Set camera controls
    controls = {}

    # Auto Exposure Enable/Disable
    controls["AeEnable"] = videoSettings['AeEnable']

    # Auto Exposure Mode (only if AeEnable is True)
    if videoSettings['AeEnable']:
        controls["AeExposureMode"] = videoSettings['AeExposureMode']

    # Auto White Balance Enable/Disable
    controls["AwbEnable"] = videoSettings['AwbEnable']

    # Auto White Balance Mode (only if AwbEnable is True)
    if videoSettings['AwbEnable']:
        controls["AwbMode"] = videoSettings['AwbMode']

    # Analogue gain
    controls["AnalogueGain"] = videoSettings['AnalogueGain']

    # Image adjustments
    controls["Sharpness"] = videoSettings['sharpness']
    controls["Contrast"] = videoSettings['contrast']
    controls["Brightness"] = videoSettings['brightness']
    controls["Saturation"] = videoSettings['saturation']

    camera.set_controls(controls)

    # Handle flip transformations
    transform = {}
    if videoSettings['vflip']:
        transform['vflip'] = True
    if videoSettings.get('hflip', False):
        transform['hflip'] = True
    if transform:
        camera.transform = transform

    # Map quality string to Quality enum
    quality_map = {
        'very_low': Quality.VERY_LOW,
        'low': Quality.LOW,
        'medium': Quality.MEDIUM,
        'high': Quality.HIGH,
        'very_high': Quality.VERY_HIGH
    }
    quality_setting = quality_map.get(videoSettings['quality'], Quality.MEDIUM)

    # Select encoder based on format
    if videoSettings['format'] == 'h264':
        encoder = H264Encoder()
    elif videoSettings['format'] == 'mjpeg':
        encoder = MJPEGEncoder()

    # Start recording
    camera.start()
    time.sleep(2)  # Allow camera to warm up and adjust settings

    # Clear frame metadata for this video
    global frame_metadata, frame_counter
    frame_metadata.clear()
    frame_counter = 0

    # Register callback to capture frame metadata
    camera.post_callback = capture_frame_metadata

    # Record video
    output = FileOutput(videofilename)
    video_start_time = datetime.now().isoformat()
    camera.start_recording(encoder, output, quality_setting)
    time.sleep(videoSettings['duration'])
    camera.stop_recording()
    camera.stop()
    camera.close()

    # Save frame metadata to JSON file
    metadata_filename = videofilename.replace('.' + videoSettings['format'], '_metadata.json')

    # Calculate statistics
    expected_frames = videoSettings['duration'] * videoSettings['frameRate']
    actual_frames = len(frame_metadata)

    try:
        with open(metadata_filename, 'w') as f:
            json.dump({
                'video_file': os.path.basename(videofilename),
                'start_time': video_start_time,
                'duration_sec': videoSettings['duration'],
                'expected_frame_rate': videoSettings['frameRate'],
                'expected_frames': expected_frames,
                'actual_frames': actual_frames,
                'resolution': videoSettings['resolution'],
                'frames': frame_metadata
            }, f, indent=2)

        # Note: frame_sequence is a manual counter and won't have gaps
        # Dropped frames are detected by comparing expected vs actual frame counts
        # or by analyzing gaps in sensor_timestamp_us

        logging.info(f"Frame metadata saved: {metadata_filename}")
        logging.info(f"Frame stats: Expected={expected_frames}, Actual={actual_frames}, Dropped={expected_frames - actual_frames}")

        if actual_frames < expected_frames * 0.95:  # More than 5% frames dropped
            logging.warning(f"Significant frame loss: {expected_frames - actual_frames} frames dropped ({100 * (expected_frames - actual_frames) / expected_frames:.1f}%)")

    except Exception as e:
        logging.error(f"Failed to save frame metadata: {e}")

    # Update iterator file
    iterFile = open(os.path.join(curDir, iterFileName), 'w')
    iterNumber += 1
    iterFile.write(str(iterNumber))
    iterFile.close()

def isCameraOperational():
    try:
        camera = Picamera2()
        camera.close()
        return True
    except BaseException as e:
        logging.error(str(e))
        return False

def captureVideo_loop(outDir, iterFileName, iterations=0, videoSettings=0, flagname=''):
    # Load default settings if nothing else provided
    if videoSettings == 0:
        videoSettings = initVideoSettings()
    # Loop
    if iterations == 0:  # Indefinite loop if no iterations provided
        loop = True
        while loop:
            captureVideo(outDir, iterFileName, videoSettings, flagname=flagname)
    elif iterations > 0:  # Finite loop if iterations provided
        for it in range(iterations):
            captureVideo(outDir, iterFileName, videoSettings, flagname=flagname)

def captureVideo_test(outDir, iterFileName, duration=10, flagname=''):

    # Test brightness (range: -1.0 to 1.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [-1.0, -0.5, 0.0, 0.5, 1.0]
    for param in paramVals:
        videoSettings['brightness'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test contrast (range: 0.0 to 32.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.5, 1.0, 1.5, 2.0, 4.0]
    for param in paramVals:
        videoSettings['contrast'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test saturation (range: 0.0 to 32.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.0, 0.5, 1.0, 2.0, 4.0]
    for param in paramVals:
        videoSettings['saturation'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test sharpness (range: 0.0 to 16.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.0, 1.0, 2.0, 4.0, 8.0]
    for param in paramVals:
        videoSettings['sharpness'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AnalogueGain (range: 1.0 to 16.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [1.0, 2.0, 4.0, 8.0, 12.0, 16.0]
    for param in paramVals:
        videoSettings['AnalogueGain'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AeExposureMode (0: Normal, 1: Short, 2: Long)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0, 1, 2]
    for param in paramVals:
        videoSettings['AeExposureMode'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AwbMode (0: Auto, 1: Tungsten, 2: Fluorescent, 3: Indoor, 4: Daylight, 5: Cloudy)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0, 1, 2, 3, 4, 5]
    for param in paramVals:
        videoSettings['AwbMode'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test quality levels
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = ['very_low', 'low', 'medium', 'high', 'very_high']
    for param in paramVals:
        videoSettings['quality'] = param
        captureVideo_loop(outDir, iterFileName, iterations=1, videoSettings=videoSettings, flagname=flagname)

def main():
    # Load configuration
    paths = config.get_paths()
    buzzer_config = config.get_buzzer_settings()
    FishCamID = config.get_fishcam_id()

    # Get paths from configuration
    outDir = paths['output_dir']
    logDir = paths['log_dir']
    iterFileName = paths['iterator_file']
    BuzzerEnabled = buzzer_config['enabled']
    BuzzerIterationPeriod = buzzer_config['iteration_period']

    # Start logs
    if os.path.isdir(logDir) == False:
        os.mkdir(logDir)
    log_filename = os.path.join(logDir, time.strftime('%Y%m%dT%H%M%S') + '.log')
    logging.basicConfig(
        filename=log_filename,
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    logging.info('Video acquisition started')
    logging.info(f'FishCam ID: {FishCamID}')
    if os.path.isdir(outDir) == False:
        os.mkdir(outDir)
    try:
        curDir = os.getcwd()  # get current working directory
        # get iteration number
        iterFile = open(os.path.join(curDir, iterFileName), 'r')
        iterNumber = iterFile.read()
        iterFile.close()
        # Creates output folder for this session based on the iteration number
        subFolderName = iterNumber
        outDir = os.path.join(outDir, subFolderName)
        if os.path.isdir(outDir) == False:
            os.mkdir(outDir)

        # Infinite loop
        BuzzerIdx = 0
        while True:

            # Ring buzzer
            if BuzzerIdx == 0 and BuzzerEnabled:
                camOK = isCameraOperational()  # checks that camera is working

                if camOK == True:  # rings the buzzer only if camera is confirmed to be working
                    logging.info('Buzzer turned ON')
                    pid = subprocess.Popen([sys.executable, 'runBuzzer.py', log_filename])

            # Capture video
            captureVideo_loop(outDir, iterFileName, iterations=0, flagname=FishCamID)  # default settings

            # Increment buzzer index
            BuzzerIdx += 1
            if BuzzerIdx == BuzzerIterationPeriod:
                BuzzerIdx = 0

    except BaseException as e:
        logging.error(str(e))

if __name__ == '__main__':
    main()