#!/bin/bash
# CYBERBOY COMMAND MENU
# Toggle: pressing Home again closes the menu

# Toggle logic - if already running, kill it
if pgrep -f "wofi.*CMDS>" >/dev/null; then
    pkill -f "wofi.*CMDS>"
    exit 0
fi

# Define commands: "Display Name|Key Combo|Command"
COMMANDS=(
    "App Launcher|W+Space|wofi --show drun"
    "Retro Games|W+G|retroarch"
    "Voice Input|W+V|python3 /home/alfonso/customization/voice_input.py"
    "Battery|W+B|python3 /home/alfonso/customization/battery_overlay.py"
    "System HUD|W+O|python3 /home/alfonso/customization/system_hud.py"
    "Power Menu|W+X|/home/alfonso/customization/power_menu.sh"
    "NetRunner|W+N|foot -e python3 /home/alfonso/customization/netrunner.py"
    "Screen Sleep|W+S|sh -c 'wlopm | grep -q off && wlopm --on DSI-1 || wlopm --off DSI-1'"
    "Fullscreen|W+F|labwc-action ToggleFullscreen"
    "Minimize|W+H|labwc-action Iconify"
    "Left Click|W+Enter|wlrctl pointer click left"
    "Right Click|W+Back|wlrctl pointer click right"
    "Mouse Up|W+Up|wlrctl pointer move 0 -20"
    "Mouse Down|W+Down|wlrctl pointer move 0 20"
    "Mouse Left|W+Left|wlrctl pointer move -20 0"
    "Mouse Right|W+Right|wlrctl pointer move 20 0"
    "Scroll Up|W+PgUp|wlrctl pointer scroll 0 -5"
    "Scroll Down|W+PgDn|wlrctl pointer scroll 0 5"
)

# Build menu entries
MENU=""
for entry in "${COMMANDS[@]}"; do
    IFS='|' read -r name key cmd <<< "$entry"
    MENU+="$name [$key]\n"
done

# Show wofi menu and get selection
SELECTION=$(echo -e "$MENU" | wofi --dmenu \
    --prompt "CMDS>" \
    --cache-file /dev/null \
    --width 280 \
    --height 420 \
    --location center)

# Exit if nothing selected
[ -z "$SELECTION" ] && exit 0

# Extract the command name from selection
SELECTED_NAME=$(echo "$SELECTION" | sed 's/ \[.*//g')

# Find and execute the matching command
for entry in "${COMMANDS[@]}"; do
    IFS='|' read -r name key cmd <<< "$entry"
    if [ "$name" = "$SELECTED_NAME" ]; then
        if [[ "$cmd" == labwc-action* ]]; then
            ACTION=$(echo "$cmd" | cut -d' ' -f2)
            case "$ACTION" in
                ToggleFullscreen) wtype -M logo -k f -m logo ;;
                Iconify) wtype -M logo -k h -m logo ;;
            esac
        else
            eval "$cmd" &
        fi
        exit 0
    fi
done
