#!/usr/bin/env python3
"""
Battery status helper for conky - outputs battery info with time remaining.
Reads state from ups_tray.py daemon via shared file.
"""

import sys
import json

# Shared state file written by ups_tray.py
BATTERY_STATE_FILE = "/tmp/cyberboy_battery_state.json"

try:
    with open(BATTERY_STATE_FILE, "r") as f:
        state = json.load(f)

    percent = state.get("percent", 0)
    charging = state.get("charging", False)
    time_str = state.get("time_remaining", "")

    # Status indicator
    status = " CHG" if charging else ""

    # Output formatted for conky (execpi interprets ${color} codes)
    print(f"> {percent}%{status}")
    if time_str:
        print(f"${{color4}}  {time_str}")

except FileNotFoundError:
    print("> N/A")
    print("${color4}  tray not running")
except json.JSONDecodeError:
    print("> ERR")
except Exception as e:
    print("> ERR")
