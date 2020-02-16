from picamera import PiCamera
import time
from datetime import datetime
import os
import logging
import subprocess
import sys

def initVideoSettings():
    videoSettings = {
        'duration': 300,      # files duration in sec
        'resolution': (1600,1200),
        'frameRate': 10,      # frame rate fps
        'quality': 20,        # 1 = best quality, 20 - ok, 30 poorer quality
        'format': 'h264',     # 'h264', 'mjpeg'
        'exposure': 'night',  # 'auto', 'night','backlight'
        'AWB': 'auto',      # 'auto', 'cloudy', 'sunlight'
        'sharpness': 0,       # integer between -100 and 100, auto: 0 
        'contrast': 0,        # integer between -100 and 100, auto: 0 
        'brightness': 50,     # integer between 0 and 100, auto: 0
        'saturation': 0,      # integer between -100 and 100, auto: 0
        'ISO': 400,             # low sensitivity: 100, high sensitivity: 400,800, auto: 0
        'vflip': False
        }
    return videoSettings

def captureVideo(outDir,iterFileName,videoSettings,flagname=''):
    # Open iterator file for output filenames
    curDir = os.getcwd()
    iterFile = open(os.path.join(curDir,iterFileName),'r') 
    iterNumber = iterFile.read()
    if len(iterNumber) == 0:
        iterNumber = 1
    else:
        iterNumber = int(iterNumber)
    iterFile.close()
    # Get current time string for the file names
    now = datetime.now()
    timeStampStr = now.strftime("%Y%m%dT%H%M%S.%fZ")
    if len(flagname)>0:
        flagname='_' + flagname
    videofilename = os.path.join(outDir,str(iterNumber) + flagname + '_' + timeStampStr + '_' + str(videoSettings['resolution'][0]) + 'x' + str(videoSettings['resolution'][1]) + '_awb-' + videoSettings['AWB'] + '_exp-' + videoSettings['exposure'] + '_fr-' + str(videoSettings['frameRate']) + '_q-' + str(videoSettings['quality']) + '_sh-' + str(videoSettings['sharpness']) + '_b-' + str(videoSettings['brightness']) + '_c-' + str(videoSettings['contrast']) + '_i-' + str(videoSettings['ISO']) + '_sat-' + str(videoSettings['saturation'])  + '.' + videoSettings['format'])
    print(videofilename)
    logging.info(videofilename)
    
    # Capture video
    camera = PiCamera()
    camera.framerate = videoSettings['frameRate']
    camera.resolution = videoSettings['resolution']
    camera.exposure_mode = videoSettings['exposure']
    camera.awb_mode = videoSettings['AWB']
    camera.vflip = videoSettings['vflip']
    camera.sharpness = videoSettings['sharpness']
    camera.contrast = videoSettings['contrast']
    camera.brightness = videoSettings['brightness']
    camera.saturation = videoSettings['saturation']
    camera.iso = videoSettings['ISO']    
    camera.start_recording(videofilename,format=videoSettings['format'], quality=videoSettings['quality'])
    camera.wait_recording(videoSettings['duration'])
    camera.stop_recording()
    camera.close()    
    # Updates iterator file
    iterFile = open(os.path.join(curDir,iterFileName),'w') 
    iterNumber += 1
    iterFile.write(str(iterNumber)) 
    iterFile.close()

def isCameraOperational():
    try:
        camera = PiCamera()
        camera.close()
        return True
    except BaseException as e:
        logging.error(str(e))
        return False

def captureVideo_loop(outDir,iterFileName,iterations=0, videoSettings=0,flagname=''):  
    # Load default settings if nothing else provided
    if videoSettings == 0:
        videoSettings = initVideoSettings()   
    # Loop
    if iterations == 0:  # Indefinite loop if no iterations provided
        loop= True
        while loop:
            captureVideo(outDir,iterFileName,videoSettings,flagname=flagname)
    elif iterations > 0:  # Finite loop if iterations provided
        for it in range(iterations):
            captureVideo(outDir,iterFileName,videoSettings,flagname=flagname)


def captureVideo_test(outDir,iterFileName,duration=10,flagname=''):    
    
    # Test brightness
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration
    paramVals = range(40,105,5)
    for param in paramVals:        
        videoSettings['brightness'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname)     
    
    # Test contrast
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration
    paramVals = range(-20,120,20)        
    for param in paramVals:        
        videoSettings['contrast'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname)
    
    # Test saturation
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration
    paramVals = range(-100,120,20)        
    for param in paramVals:        
        videoSettings['saturation'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname)
        
    # Test sharpness
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration
    paramVals = range(-100,120,20)        
    for param in paramVals:        
        videoSettings['sharpness'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname)

    # Test ISO
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration    
    paramVals = [100,200,320,400,500,640,800]    
    for param in paramVals:        
        videoSettings['ISO'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1, videoSettings=videoSettings,flagname=flagname) 

    # Test exposure
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration    
    paramVals = ['auto', 'night','backlight']    
    for param in paramVals:        
        videoSettings['exposure'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname) 
    # Test AWB
    videoSettings = initVideoSettings()   
    videoSettings['duration'] = duration    
    paramVals = ['auto', 'cloudy', 'sunlight']    
    for param in paramVals:        
        videoSettings['AWB'] = param
        captureVideo_loop(outDir,iterFileName,iterations=1,videoSettings=videoSettings,flagname=flagname) 


def main():
    # Parameters 
    outDir=r'../data'
    logDir=r'../logs'
    iterFileName = r'iterator.config'
    FishCamIDFileName = r'FishCamID.config'
    BuzzerEnabled = True
    BuzzerIterationPeriod = -1
    
    # Start logs
    if os.path.isdir(logDir) == False:
        os.mkdir(logDir)
    logging.basicConfig(filename=os.path.join(logDir,time.strftime('%Y%m%dT%H%M%S') +'.log'), level=logging.DEBUG,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.info('Video acquisition started')
    if os.path.isdir(outDir) == False:
        os.mkdir(outDir)
    try: 
        curDir = os.getcwd() # get current working directory
        # Get FishCam ID
        FishCamIDFile = open(os.path.join(curDir,FishCamIDFileName),'r') # Open FishCam ID file for output filenames
        FishCamID = FishCamIDFile.read()        
        # get iteration number
        iterFile = open(os.path.join(curDir,iterFileName),'r') # Open iterator file for output filenames
        iterNumber = iterFile.read()
        # Creates output folder for this session based on the iteration number            
        subFolderName = iterNumber
        outDir = os.path.join(outDir,subFolderName)
        if os.path.isdir(outDir) == False:
            os.mkdir(outDir)
        
        # Infinite loop
        BuzzerIdx=0
        while True:
            
            # Ring buzzer            
            if BuzzerIdx == 0 and BuzzerEnabled:
                camOK = isCameraOperational() # checks that camera is working
                #print(camOK)
                
                ## DEBUG ##
                #camOK =True
                #print('Debuging mode - camOK always set to TRUE')
                #print(camOK)
                ## DEBUG ##
                
                if camOK == True: # rings the buzzer only if camera is confirmed to be working (needed for pre-deploymnet verification)
                    logging.info('Buzzer turned ON')                    
                    pid = subprocess.Popen([sys.executable, 'runBuzzer.py'])
                    
                    
            # Capture video            
            captureVideo_loop(outDir,iterFileName,iterations=0,flagname=FishCamID)  # default settings
            
            ## DEBUG
            #import datetime
            #print('Camera starts doing its thing')
            #print(datetime.datetime.now())
            #time.sleep(300)
            #print('Camera stops doing its thing')
            #print(datetime.datetime.now())

            
            # Adjust camera parameters
            
            # Increment buzzer index
            BuzzerIdx+=1
            if BuzzerIdx == BuzzerIterationPeriod:
                BuzzerIdx = 0
            
    except BaseException as e:
        logging.error(str(e))

if __name__ == '__main__':   
    main()