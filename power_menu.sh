#!/bin/bash
# CYBERBOY Power Menu - Wofi-based power options

OPTIONS="⏻  Shutdown\n⟳  Reboot\n⏾  Sleep\n🔒  Lock Screen\n⏏  Logout"

CHOICE=$(echo -e "$OPTIONS" | wofi --dmenu --prompt "POWER>" --width 300 --height 250 --cache-file /dev/null)

case "$CHOICE" in
    "⏻  Shutdown")
        systemctl poweroff
        ;;
    "⟳  Reboot")
        systemctl reboot
        ;;
    "⏾  Sleep")
        systemctl suspend
        ;;
    "🔒  Lock Screen")
        # Turn off display (simple lock for now)
        wlopm --off DSI-1
        ;;
    "⏏  Logout")
        labwc --exit
        ;;
esac
