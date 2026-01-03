#!/bin/bash
cd /home/fishcam/Desktop/FishCam
git fetch origin
git reset --hard origin/main
git clean -fd -e data -e logs
