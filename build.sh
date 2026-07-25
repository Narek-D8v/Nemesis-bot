#!/bin/bash
apt-get update -qq && apt-get install -y -qq ffmpeg nodejs 2>/dev/null
pip install -r requirements.txt
