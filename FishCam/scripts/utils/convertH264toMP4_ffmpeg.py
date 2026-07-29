# -*- coding: utf-8 -*-
"""
Created on Thu Nov 10 13:38:15 2022

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
# This script needs ffmpeg on the computer.

## Input parameters:
ffmpeg_path = r"C:\Users\xavier.mouy\Documents\Software\ffmpeg\bin\ffmpeg.exe"
indir = r"C:\Users\xavier.mouy\Documents\Projects\2022_DFO_fish_catalog\videos_Darienne\test h264"  # main directory where the h264 files are (it will go through all subfolders)
outdir = r"C:\Users\xavier.mouy\Documents\Projects\2022_DFO_fish_catalog\videos_Darienne\mp4"  # folder where the mp4 files will be saved
video_fps = 10  # Frame per second
video_ext = "*.h264"

##############################################################################
##############################################################################

## Loop through h264 files ###################################################
for root, directories, filenames in os.walk(indir):
    directories.sort()
    for filename in sorted(filenames):
        if fnmatch.fnmatch(filename, video_ext):
            fname = os.path.join(root, filename)
            filerootname = os.path.splitext(os.path.basename(fname))[0]
            print(" ")
            print("--------------------------------------------")
            print(fname)
            # This is the code that works in the terminal window for conversion: NAME OF WORKING DIRECTORY HERE>ffmpeg -framerate 10 -i test.h264 test2.mp4
            cmd_string = [
                ffmpeg_path,
                "-framerate",
                str(video_fps),
                "-i",
                fname,
                os.path.join(outdir, filerootname + ".mp4"),
            ]
            result = subprocess.run(
                cmd_string, stdout=subprocess.PIPE, text=True
            )
            print(result.stdout)
