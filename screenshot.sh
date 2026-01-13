#!/bin/bash
FILENAME=~/screenshots/screenshot-$(date +%Y%m%d-%H%M%S).png
grim "$FILENAME" && notify-send "Screenshot saved" "$FILENAME" -t 2000
