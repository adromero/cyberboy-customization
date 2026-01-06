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

# Import shared battery learning module
try:
    from battery_learning import (
        get_battery_learning, voltage_to_percent, smoothed_voltage_to_percent,
        SHUNT_OHMS, I2C_ADDRESS, I2C_BUS,
        LOW_VOLTAGE_WARN, CRITICAL_VOLTAGE
    )
    HAS_LEARNING = True
except ImportError:
    HAS_LEARNING = False
    SHUNT_OHMS = 0.1
    I2C_ADDRESS = 0x41
    I2C_BUS = 1
    LOW_VOLTAGE_WARN = 10.2
    CRITICAL_VOLTAGE = 9.6

    # Fallback discharge curve
    DISCHARGE_CURVE = [
        (12.6, 100), (12.4, 92), (12.0, 78), (11.7, 62),
        (11.4, 50), (11.1, 40), (10.8, 28), (10.5, 18),
        (10.2, 10), (9.9, 5), (9.6, 2), (9.0, 0),
    ]

    def voltage_to_percent(voltage):
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

PID_FILE = "/tmp/battery_overlay.pid"

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

        # Get battery learning instance
        self.learning = get_battery_learning() if HAS_LEARNING else None

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

        # Container for stacked labels
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.box.set_halign(Gtk.Align.END)
        self.add(self.box)

        # Main percentage label
        self.label = Gtk.Label()
        self.label.set_markup('<span font="14" weight="bold" foreground="#00FF00">--%</span>')
        self.label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.label, False, False, 0)

        # Time remaining label (smaller)
        self.time_label = Gtk.Label()
        self.time_label.set_markup('<span font="9" foreground="#888888"></span>')
        self.time_label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.time_label, False, False, 0)

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
            self.label.set_markup('<span font="14" weight="bold" foreground="#888888">N/A</span>')
            self.time_label.set_markup('')
            return True

        try:
            voltage = self.ina.voltage()
            current = self.ina.current()

            # Charging if current > 10mA
            charging = current > 10

            # Calculate percentage using discharge curve (smoothed if available)
            if HAS_LEARNING:
                percent = smoothed_voltage_to_percent(voltage, charging)
            else:
                percent = voltage_to_percent(voltage)
            color = self.get_color(percent, charging)

            # Record sample for learning
            if self.learning:
                power = self.ina.power()
                self.learning.record_sample(voltage, current, power)

            # Show charging indicator
            charge_icon = " +" if charging else ""
            self.label.set_markup(
                f'<span font="14" weight="bold" foreground="{color}">'
                f'{percent:.0f}%{charge_icon}</span>'
            )

            # Show time remaining
            if self.learning:
                time_str = self.learning.format_time_remaining(percent, current)
                if time_str:
                    time_color = "#00BFFF" if charging else "#AAAAAA"
                    self.time_label.set_markup(
                        f'<span font="9" foreground="{time_color}">{time_str}</span>'
                    )
                else:
                    self.time_label.set_markup('')
            else:
                self.time_label.set_markup('')

        except Exception as e:
            self.label.set_markup('<span font="14" weight="bold" foreground="#FF4444">ERR</span>')
            self.time_label.set_markup('')

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
