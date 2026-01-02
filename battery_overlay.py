#!/usr/bin/env python3
"""
Battery Percentage Overlay - Layer shell overlay showing battery %.
Toggle with Super+b.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib, Pango
import os
import signal
import sys

try:
    from ina219 import INA219, DeviceRangeError
    HAS_INA219 = True
except ImportError:
    HAS_INA219 = False

PID_FILE = "/tmp/battery_overlay.pid"

# INA219 Configuration (same as ups_tray.py)
SHUNT_OHMS = 0.1
I2C_ADDRESS = 0x41
I2C_BUS = 1
VOLT_MIN = 9.0
VOLT_MAX = 12.6

# Low voltage warning thresholds
LOW_VOLTAGE_WARN = 10.2   # ~20% actual capacity
CRITICAL_VOLTAGE = 9.6    # ~10% actual capacity

# 3S Li-ion discharge curve lookup (voltage -> percent)
DISCHARGE_CURVE = [
    (12.6, 100),
    (12.4, 95),
    (12.0, 80),
    (11.5, 60),
    (11.1, 50),  # nominal voltage
    (10.8, 40),
    (10.5, 30),
    (10.2, 20),
    (10.0, 15),
    (9.6, 10),
    (9.3, 5),
    (9.0, 0),
]

def voltage_to_percent(voltage):
    """Convert voltage to percentage using Li-ion discharge curve."""
    if voltage >= DISCHARGE_CURVE[0][0]:
        return 100
    if voltage <= DISCHARGE_CURVE[-1][0]:
        return 0

    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if v_low <= voltage <= v_high:
            ratio = (voltage - v_low) / (v_high - v_low)
            return p_low + ratio * (p_high - p_low)
    return 0

# Overlay styling
MARGIN_TOP = 10
MARGIN_RIGHT = 10

class BatteryOverlay(Gtk.Window):
    def __init__(self):
        super().__init__()

        # Initialize INA219
        self.ina = None
        if HAS_INA219:
            try:
                self.ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
                self.ina.configure()
            except Exception as e:
                print(f"INA219 error: {e}", file=sys.stderr)

        # Set up layer shell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, MARGIN_TOP)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, MARGIN_RIGHT)
        GtkLayerShell.set_exclusive_zone(self, 0)

        # Transparent background
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Label for battery percentage
        self.label = Gtk.Label()
        self.label.set_markup('<span font="16" weight="bold" foreground="#00FF00">--%</span>')
        self.add(self.label)

        # Update immediately and every 5 seconds
        self.update_battery()
        GLib.timeout_add_seconds(5, self.update_battery)

        self.show_all()

    def get_color(self, percent, charging):
        """Get color based on battery level."""
        if charging:
            return "#00BFFF"  # Cyan for charging
        elif percent >= 50:
            return "#00FF00"  # Green
        elif percent >= 20:
            return "#FFD700"  # Yellow/gold
        else:
            return "#FF4444"  # Red

    def update_battery(self):
        if not self.ina:
            self.label.set_markup('<span font="16" weight="bold" foreground="#888888">N/A</span>')
            return True

        try:
            voltage = self.ina.voltage()
            current = self.ina.current()

            # Calculate percentage using discharge curve
            percent = voltage_to_percent(voltage)

            # Charging if current > 10mA
            charging = current > 10
            color = self.get_color(percent, charging)

            # Show charging indicator
            charge_icon = "⚡" if charging else ""
            self.label.set_markup(
                f'<span font="14" weight="bold" foreground="{color}">'
                f'{percent:.0f}%{charge_icon}</span>'
            )

        except Exception as e:
            self.label.set_markup('<span font="14" weight="bold" foreground="#FF4444">ERR</span>')

        return True

def is_running():
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            os.remove(PID_FILE)
    return None

def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup(*args):
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    Gtk.main_quit()

def main():
    other_pid = is_running()

    if other_pid:
        # Toggle off - kill the other instance
        try:
            os.kill(other_pid, signal.SIGTERM)
            print("Battery overlay closed")
        except Exception:
            pass
        return

    # Start overlay
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    write_pid()

    win = BatteryOverlay()
    win.connect("destroy", Gtk.main_quit)

    import atexit
    atexit.register(cleanup)

    Gtk.main()

if __name__ == "__main__":
    main()
