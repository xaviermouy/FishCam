#!/bin/bash
cd /home/fishcam/Desktop/FishCam
git fetch origin
git reset --hard origin
git clean -fd
