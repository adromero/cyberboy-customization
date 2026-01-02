#!/usr/bin/env python3
"""
Voice Input Indicator - Layer shell overlay for voice input status.
Shows a small colored dot in the upper right corner.
- Yellow: listening/ready
- Green: processing speech
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib
import os
import signal
import sys

STATE_FILE = "/tmp/voice_indicator_state"
SIZE = 16
MARGIN = 10

COLORS = {
    "yellow": (1.0, 0.85, 0.0),   # Listening
    "green": (0.2, 0.9, 0.2),     # Processing
    "off": None
}

class IndicatorWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.color = COLORS["yellow"]

        # Set up layer shell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, MARGIN)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, MARGIN)
        GtkLayerShell.set_exclusive_zone(self, 0)  # Don't push other windows

        # Transparent background
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_size_request(SIZE, SIZE)
        self.drawing_area.connect("draw", self.on_draw)
        self.add(self.drawing_area)

        # Watch state file
        GLib.timeout_add(100, self.check_state)

        self.show_all()

    def on_draw(self, widget, cr):
        if self.color is None:
            return

        r, g, b = self.color

        # Draw circle with glow effect
        cr.set_source_rgba(r, g, b, 0.3)
        cr.arc(SIZE/2, SIZE/2, SIZE/2, 0, 2 * 3.14159)
        cr.fill()

        cr.set_source_rgba(r, g, b, 1.0)
        cr.arc(SIZE/2, SIZE/2, SIZE/3, 0, 2 * 3.14159)
        cr.fill()

    def check_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = f.read().strip()
                if state in COLORS:
                    new_color = COLORS[state]
                    if new_color != self.color:
                        self.color = new_color
                        if self.color is None:
                            self.destroy()
                            return False
                        self.drawing_area.queue_draw()
        except Exception:
            pass
        return True

def cleanup(*args):
    try:
        os.remove(STATE_FILE)
    except Exception:
        pass
    Gtk.main_quit()

def main():
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Set initial state
    with open(STATE_FILE, "w") as f:
        f.write("yellow")

    win = IndicatorWindow()
    win.connect("destroy", Gtk.main_quit)

    Gtk.main()
    cleanup()

if __name__ == "__main__":
    main()
