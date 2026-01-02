#!/usr/bin/env python3
"""UPS Battery Tray Indicator for Raspberry Pi"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3, GLib
from ina219 import INA219, DeviceRangeError

# INA219 Configuration
SHUNT_OHMS = 0.1
I2C_ADDRESS = 0x41
I2C_BUS = 1

# Battery voltage range (3S Li-ion: 9.0V empty, 12.6V full)
VOLT_MIN = 9.0
VOLT_MAX = 12.6

# Low voltage warning thresholds
LOW_VOLTAGE_WARN = 10.2   # ~20% actual capacity
CRITICAL_VOLTAGE = 9.6    # ~10% actual capacity

# 3S Li-ion discharge curve lookup (voltage -> percent)
# Based on typical Li-ion discharge characteristics
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

    # Linear interpolation between curve points
    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if v_low <= voltage <= v_high:
            ratio = (voltage - v_low) / (v_high - v_low)
            return p_low + ratio * (p_high - p_low)
    return 0

class UPSIndicator:
    def __init__(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "ups-battery",
            "battery-full",
            AyatanaAppIndicator3.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        # Create menu
        self.menu = Gtk.Menu()

        self.percent_item = Gtk.MenuItem(label="Battery: --%")
        self.percent_item.set_sensitive(False)
        self.menu.append(self.percent_item)

        self.voltage_item = Gtk.MenuItem(label="Voltage: --")
        self.voltage_item.set_sensitive(False)
        self.menu.append(self.voltage_item)

        self.current_item = Gtk.MenuItem(label="Current: --")
        self.current_item.set_sensitive(False)
        self.menu.append(self.current_item)

        self.power_item = Gtk.MenuItem(label="Power: --")
        self.power_item.set_sensitive(False)
        self.menu.append(self.power_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # Initialize INA219
        try:
            self.ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
            self.ina.configure()
            self.ina_ok = True
        except Exception as e:
            print(f"INA219 init error: {e}")
            self.ina_ok = False

        # Update every 5 seconds
        GLib.timeout_add_seconds(5, self.update)
        self.update()

    def get_battery_icon(self, percent, charging):
        if percent >= 80:
            level = "full"
        elif percent >= 50:
            level = "good"
        elif percent >= 20:
            level = "low"
        else:
            level = "empty"

        if charging:
            return f"battery-{level}-charging"
        return f"battery-{level}"

    def update(self):
        if not self.ina_ok:
            self.indicator.set_label("ERR", "")
            return True

        try:
            voltage = self.ina.voltage()
            current = self.ina.current()
            power = self.ina.power()

            # Calculate percentage using discharge curve
            percent = voltage_to_percent(voltage)

            # Positive current = charging (depends on wiring)
            charging = current > 10

            # Update icon with low voltage override
            if voltage <= CRITICAL_VOLTAGE and not charging:
                icon = "battery-empty"
            elif voltage <= LOW_VOLTAGE_WARN and not charging:
                icon = "battery-caution" if percent > 10 else "battery-empty"
            else:
                icon = self.get_battery_icon(percent, charging)
            self.indicator.set_icon_full(icon, f"Battery {percent:.0f}%")
            self.indicator.set_label(f"{percent:.0f}%", "")
            self.indicator.set_title(f"Battery {percent:.0f}%")

            # Update menu items
            self.percent_item.set_label(f"Battery: {percent:.0f}%")
            self.voltage_item.set_label(f"Voltage: {voltage:.2f} V")
            self.current_item.set_label(f"Current: {current:.1f} mA")
            self.power_item.set_label(f"Power: {power:.1f} mW")

        except DeviceRangeError:
            self.indicator.set_label("OVR", "")
        except Exception as e:
            print(f"Update error: {e}")
            self.indicator.set_label("ERR", "")

        return True

    def quit(self, widget):
        Gtk.main_quit()

if __name__ == "__main__":
    indicator = UPSIndicator()
    Gtk.main()
