#!/bin/bash
# CYBERBOY Gesture Daemon
# Touchscreen gestures using lisgd

# Find touchscreen device
TOUCH_DEV=$(ls /dev/input/by-id/*touch* 2>/dev/null | head -1)
if [ -z "$TOUCH_DEV" ]; then
    TOUCH_DEV="/dev/input/event6"
fi

# Gesture definitions:
# -g "nfingers,gesture,edge,distance,command"
# Gestures: LR, RL, DU, UD (and diagonals DLUR, DRUL, URDL, ULDR)
# Edge: * (any), N (none), L, R, T, B, TL, TR, BL, BR
# Distance: * (any), S (short), M (medium), L (large)

lisgd -d "$TOUCH_DEV" \
    -g "1,RL,*,*,wlrctl pointer scroll 0 5" \
    -g "1,LR,*,*,wlrctl pointer scroll 0 -5" \
    -g "2,LR,*,*,labwc --exit || true" \
    -g "2,RL,*,*,wofi --show drun" \
    -g "2,DU,*,*,$HOME/customization/power_menu.sh" \
    -g "2,UD,*,*,wlrctl pointer click left" \
    -g "3,LR,*,*,wtype -k Tab" \
    -g "3,RL,*,*,wtype -k Escape" \
    -g "3,UD,*,*,python3 $HOME/customization/system_hud.py" \
    -g "3,DU,*,*,foot" \
    -t 300 \
    -m 500
