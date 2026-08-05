from picamera2 import Picamera2
import signal
import threading
from picamera2.encoders import H264Encoder, MJPEGEncoder, Quality
from picamera2.outputs import FileOutput
import time
from datetime import datetime
import os
import logging
import sys
import json
from pathlib import Path
import config

# Global list to store frame metadata
frame_metadata = []
frame_counter = 0

# Shutdown event — set by the signal handler so the recording loop
# exits cleanly without touching camera objects from signal context.
_shutdown_event = threading.Event()

def shutdown_handler(signum, frame):
    """Handle shutdown signals from WittyPi or the OS.

    Only sets the event; all camera cleanup happens in the normal
    finally path so Picamera2 threads are never interrupted mid-flight.
    """
    logging.info(f"Received signal {signum} — stopping recording and shutting down...")
    _shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT,  shutdown_handler)

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

def captureVideo(outDir, videoSettings, flagname=''):
    # Get current time string for the file names
    now = datetime.now()
    timeStampStr = now.strftime("%Y%m%dT%H%M%S.%fZ")
    suffix = '_' + flagname if len(flagname) > 0 else ''

    videofilename = os.path.join(
        outDir,
        timeStampStr + suffix + '_' +
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

    camera = Picamera2()
    try:
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
        else:
            raise ValueError(f"Unsupported video format: '{videoSettings['format']}'. Use 'h264' or 'mjpeg'.")

        # Start recording
        camera.start()
        if _shutdown_event.wait(timeout=2):  # warmup — exits early if shutdown signalled
            camera.stop()
            return  # no recording was made; skip metadata

        # Clear frame metadata for this video
        global frame_metadata, frame_counter
        frame_metadata.clear()
        frame_counter = 0

        # Register callback to capture frame metadata
        camera.post_callback = capture_frame_metadata

        # Record video
        output = FileOutput(videofilename)
        video_start_time = datetime.now().astimezone().strftime('%Y%m%dT%H%M%S.%f%z')
        camera.start_recording(encoder, output, quality_setting)
        _shutdown_event.wait(timeout=videoSettings['duration'])  # returns early on shutdown
        camera.stop_recording()
        camera.stop()
    finally:
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

def isCameraOperational():
    try:
        camera = Picamera2()
        camera.close()
        return True
    except BaseException as e:
        logging.error(str(e))
        return False

def captureVideo_loop(outDir, iterations=0, videoSettings=0, flagname=''):
    # Load default settings if nothing else provided
    if videoSettings == 0:
        videoSettings = initVideoSettings()

    MAX_CONSECUTIVE_FAILURES = 5  # give up after this many back-to-back errors
    RETRY_DELAY_S = 15            # wait between retries (lets kernel clean up state)

    # Loop
    if iterations == 0:  # Indefinite loop if no iterations provided
        consecutive_failures = 0
        while not _shutdown_event.is_set():
            try:
                captureVideo(outDir, videoSettings, flagname=flagname)
                consecutive_failures = 0  # reset on successful clip
            except Exception as e:
                if _shutdown_event.is_set():
                    break
                consecutive_failures += 1
                logging.error(
                    f"Camera error (failure {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logging.error(
                        "Too many consecutive camera failures — stopping video acquisition."
                    )
                    raise
                logging.info(f"Retrying camera in {RETRY_DELAY_S}s...")
                _shutdown_event.wait(timeout=RETRY_DELAY_S)  # interruptible sleep

    elif iterations > 0:  # Finite loop if iterations provided
        for it in range(iterations):
            if _shutdown_event.is_set():
                break
            captureVideo(outDir, videoSettings, flagname=flagname)

def captureVideo_test(outDir, duration=10, flagname=''):

    # Test brightness (range: -1.0 to 1.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [-1.0, -0.5, 0.0, 0.5, 1.0]
    for param in paramVals:
        videoSettings['brightness'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test contrast (range: 0.0 to 32.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.5, 1.0, 1.5, 2.0, 4.0]
    for param in paramVals:
        videoSettings['contrast'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test saturation (range: 0.0 to 32.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.0, 0.5, 1.0, 2.0, 4.0]
    for param in paramVals:
        videoSettings['saturation'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test sharpness (range: 0.0 to 16.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0.0, 1.0, 2.0, 4.0, 8.0]
    for param in paramVals:
        videoSettings['sharpness'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AnalogueGain (range: 1.0 to 16.0)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [1.0, 2.0, 4.0, 8.0, 12.0, 16.0]
    for param in paramVals:
        videoSettings['AnalogueGain'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AeExposureMode (0: Normal, 1: Short, 2: Long)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0, 1, 2]
    for param in paramVals:
        videoSettings['AeExposureMode'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test AwbMode (0: Auto, 1: Tungsten, 2: Fluorescent, 3: Indoor, 4: Daylight, 5: Cloudy)
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = [0, 1, 2, 3, 4, 5]
    for param in paramVals:
        videoSettings['AwbMode'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

    # Test quality levels
    videoSettings = initVideoSettings()
    videoSettings['duration'] = duration
    paramVals = ['very_low', 'low', 'medium', 'high', 'very_high']
    for param in paramVals:
        videoSettings['quality'] = param
        captureVideo_loop(outDir, iterations=1, videoSettings=videoSettings, flagname=flagname)

def main():
    paths = config.get_paths()
    FishCamID = config.get_fishcam_id()

    scriptDir = Path(__file__).parent
    outDir = str(scriptDir / paths['video_dir'])
    logDir = str(scriptDir / paths['log_dir'])

    os.makedirs(logDir, exist_ok=True)
    log_filename = os.path.join(logDir, 'video_' + FishCamID + '.log')
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )

    sessionTimestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    logging.info('=' * 60)
    logging.info('FishCam Video Acquisition')
    logging.info('=' * 60)
    logging.info(f'FishCam ID: {FishCamID}')

    os.makedirs(outDir, exist_ok=True)
    sessionFolder = sessionTimestamp
    outDir = os.path.join(outDir, sessionFolder)
    os.makedirs(outDir, exist_ok=True)
    logging.info(f'Session folder: {outDir}')

    try:
        captureVideo_loop(outDir, iterations=0, flagname=FishCamID)
    except BaseException as e:
        logging.error(str(e))
    finally:
        if _shutdown_event.is_set():
            logging.info("Shutdown signal received — recording stopped cleanly.")

if __name__ == '__main__':
    main()
