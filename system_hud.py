#!/usr/bin/env python3
"""
CYBERBOY System HUD Toggle
Toggles the conky system overlay on/off
"""

import subprocess
import sys

def is_running():
    """Check if conky is running with our config"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'conky.*cyberboy'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False

def start_hud():
    """Start the conky HUD"""
    subprocess.Popen(
        ['conky', '-c', '/home/alfonso/.config/conky/cyberboy.conf'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

def stop_hud():
    """Stop the conky HUD"""
    subprocess.run(
        ['pkill', '-f', 'conky.*cyberboy'],
        capture_output=True
    )

def main():
    if is_running():
        stop_hud()
    else:
        start_hud()

if __name__ == "__main__":
    main()
