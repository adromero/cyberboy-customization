#!/usr/bin/env python3
"""
Battery Safe Shutdown Daemon
Monitors battery voltage and initiates safe shutdown at critical level.
Run as a systemd service or from autostart.
"""

import time
import subprocess
import sys
import signal
import os

try:
    from ina219 import INA219
except ImportError:
    print("Error: ina219 library not found", file=sys.stderr)
    sys.exit(1)

from battery_learning import (
    get_battery_learning, get_hybrid_soc,
    SHUNT_OHMS, I2C_ADDRESS, I2C_BUS,
    CRITICAL_VOLTAGE
)

# Configuration
CHECK_INTERVAL = 10  # seconds between checks
SHUTDOWN_VOLTAGE = 9.6  # Voltage threshold for shutdown
SHUTDOWN_PERCENT = 3  # Percent threshold for shutdown
CONSECUTIVE_LOW = 3  # Number of consecutive low readings before shutdown
WARN_BEFORE_SHUTDOWN = True  # Send notification before shutdown

PID_FILE = "/tmp/battery_shutdown.pid"


def send_notification(title, message, urgency="critical"):
    """Send notification via mako."""
    try:
        subprocess.run(
            ["notify-send", "-u", urgency, title, message],
            timeout=5,
            capture_output=True
        )
    except Exception:
        pass


def safe_shutdown():
    """Initiate safe system shutdown."""
    print("Initiating safe shutdown due to low battery...")

    # Send final notification
    send_notification(
        "SHUTTING DOWN",
        "Battery critically low. System shutting down now.",
        urgency="critical"
    )

    # Give notification time to display
    time.sleep(2)

    # Sync filesystems
    try:
        subprocess.run(["sync"], timeout=10)
    except Exception:
        pass

    # Shutdown
    try:
        subprocess.run(["systemctl", "poweroff"], timeout=10)
    except Exception:
        # Fallback
        try:
            subprocess.run(["sudo", "poweroff"], timeout=10)
        except Exception:
            pass


def is_running():
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
    return False


def write_pid():
    """Write PID file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*args):
    """Clean up on exit."""
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    sys.exit(0)


def main():
    if is_running():
        print("Battery shutdown daemon already running", file=sys.stderr)
        sys.exit(1)

    # Set up signal handlers
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    write_pid()
    print(f"Battery shutdown daemon started (PID {os.getpid()})")
    print(f"Shutdown thresholds: {SHUTDOWN_VOLTAGE}V / {SHUTDOWN_PERCENT}%")

    # Initialize INA219
    try:
        ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
        ina.configure()
    except Exception as e:
        print(f"Error initializing INA219: {e}", file=sys.stderr)
        cleanup()

    # Get battery learning instance
    learning = get_battery_learning()

    low_count = 0
    warned = False

    while True:
        try:
            voltage = ina.voltage()
            current = ina.current()
            power = ina.power()

            # Get hybrid SOC
            percent = get_hybrid_soc(voltage, current, power)
            charging = learning.is_charging()

            # Only check for low battery when not charging
            if not charging:
                # Check if critically low
                if voltage <= SHUTDOWN_VOLTAGE or percent <= SHUTDOWN_PERCENT:
                    low_count += 1
                    print(f"Low battery detected: {voltage:.2f}V / {percent:.0f}% "
                          f"(count: {low_count}/{CONSECUTIVE_LOW})")

                    # Warn before shutdown
                    if low_count == 1 and WARN_BEFORE_SHUTDOWN and not warned:
                        send_notification(
                            "CRITICAL BATTERY",
                            f"Battery at {percent:.0f}%! Shutdown in ~{CONSECUTIVE_LOW * CHECK_INTERVAL}s",
                            urgency="critical"
                        )
                        warned = True

                    if low_count >= CONSECUTIVE_LOW:
                        safe_shutdown()
                        break
                else:
                    # Reset counter if we get a good reading
                    if low_count > 0:
                        print(f"Battery recovered: {voltage:.2f}V / {percent:.0f}%")
                    low_count = 0
                    warned = False
            else:
                # Charging - reset everything
                low_count = 0
                warned = False

        except Exception as e:
            print(f"Error reading battery: {e}", file=sys.stderr)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
