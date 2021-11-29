# -*- coding: utf-8 -*-
"""
Created on Tue Oct 23 10:12:57 2018

@author: xavier.mouy
"""
import os
import fnmatch
import subprocess

##############################################################################
##############################################################################
## Description:
# This script converts all the h264 video files recorded by the FishCam to the mp4 format.

## Requirements: 
# This script needs MP4Box to be installed on the computer. Installation file can be found here: https://gpac.wp.imt.fr/mp4box/.
# MP4Box wraps the h264 files as mp4
# Tutorial on how to use MP4Box: https://www.raspberrypi-spy.co.uk/2013/05/capturing-hd-video-with-the-pi-camera-module/:

## Input parameters:
indir = r".\data" # main directory where the h264 files are (it will go through all subfolders)
outdir= r'.\mp4' # folder where the mp4 files will be saved
video_fps = 20 # Frame per second
video_ext = "*.h264"

##############################################################################
##############################################################################

## Loop through h264 files ################################################### 
for root, directories, filenames in os.walk(indir):
    directories.sort()
    for filename in sorted(filenames):        
        if fnmatch.fnmatch(filename, video_ext):            
            fname = os.path.join(root,filename)
            filerootname = os.path.splitext(os.path.basename(fname))[0]
            print(' ')
            print('--------------------------------------------') 
            print (fname)      
            #subprocess.call(["C:\Program Files\GPAC\mp4box.exe", "-fps", str(video_fps), "-add", os.path.join(indir,infile), os.path.join(outdir,filerootname + '.mp4')])
            subprocess.call(["C:\Program Files\GPAC\mp4box.exe", "-fps", str(video_fps), "-add", fname, os.path.join(outdir,filerootname + '.mp4')])
        