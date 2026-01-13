#!/usr/bin/env python3
"""
Battery Percentage Overlay - Layer shell overlay showing battery %.
Toggle with Super+b. Reads state from ups_tray.py daemon via shared file.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib, Pango
import os
import signal
import sys
import json

# Shared state file written by ups_tray.py
BATTERY_STATE_FILE = "/tmp/cyberboy_battery_state.json"
PID_FILE = "/tmp/battery_overlay.pid"

# Overlay styling
MARGIN_TOP = 10
MARGIN_RIGHT = 10


class BatteryOverlay(Gtk.Window):
    def __init__(self):
        super().__init__()

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

    def read_battery_state(self):
        """Read battery state from shared file written by ups_tray.py."""
        try:
            with open(BATTERY_STATE_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def update_battery(self):
        state = self.read_battery_state()

        if not state:
            self.label.set_markup('<span font="14" weight="bold" foreground="#888888">N/A</span>')
            self.time_label.set_markup('<span font="9" foreground="#666666">tray not running</span>')
            return True

        percent = state.get("percent", 0)
        charging = state.get("charging", False)
        time_str = state.get("time_remaining", "")

        color = self.get_color(percent, charging)

        # Show charging indicator
        charge_icon = " +" if charging else ""
        self.label.set_markup(
            f'<span font="14" weight="bold" foreground="{color}">'
            f'{percent:.0f}%{charge_icon}</span>'
        )

        # Show time remaining
        if time_str:
            time_color = "#00BFFF" if charging else "#AAAAAA"
            self.time_label.set_markup(
                f'<span font="9" foreground="{time_color}">{time_str}</span>'
            )
        else:
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
