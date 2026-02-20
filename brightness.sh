#!/bin/bash
BRIGHTNESS_FILE="/sys/class/backlight/10-0045/brightness"
CURRENT=$(cat "$BRIGHTNESS_FILE")
STEP=25
MIN=10
MAX=255

case "$1" in
    up)
        NEW=$((CURRENT + STEP))
        [ $NEW -gt $MAX ] && NEW=$MAX
        ;;
    down)
        NEW=$((CURRENT - STEP))
        [ $NEW -lt $MIN ] && NEW=$MIN
        ;;
    *)
        exit 1
        ;;
esac

echo $NEW > "$BRIGHTNESS_FILE"
