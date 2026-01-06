#!/usr/bin/env python3
"""UPS Battery Tray Indicator for Raspberry Pi"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3, GLib
from ina219 import INA219, DeviceRangeError

# Import shared battery learning module
try:
    from battery_learning import (
        get_battery_learning, voltage_to_percent, smoothed_voltage_to_percent,
        SHUNT_OHMS, I2C_ADDRESS, I2C_BUS, NOMINAL_CAPACITY_MAH,
        LOW_VOLTAGE_WARN, CRITICAL_VOLTAGE, VOLT_MIN, VOLT_MAX
    )
    HAS_LEARNING = True
except ImportError:
    HAS_LEARNING = False
    SHUNT_OHMS = 0.1
    I2C_ADDRESS = 0x41
    I2C_BUS = 1
    VOLT_MIN = 9.0
    VOLT_MAX = 12.6
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


class UPSIndicator:
    def __init__(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "ups-battery",
            "battery-full",
            AyatanaAppIndicator3.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        # Get battery learning instance
        self.learning = get_battery_learning() if HAS_LEARNING else None

        # Create menu
        self.menu = Gtk.Menu()

        self.percent_item = Gtk.MenuItem(label="Battery: --%")
        self.percent_item.set_sensitive(False)
        self.menu.append(self.percent_item)

        self.time_item = Gtk.MenuItem(label="Time: --")
        self.time_item.set_sensitive(False)
        self.menu.append(self.time_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.voltage_item = Gtk.MenuItem(label="Voltage: --")
        self.voltage_item.set_sensitive(False)
        self.menu.append(self.voltage_item)

        self.current_item = Gtk.MenuItem(label="Current: --")
        self.current_item.set_sensitive(False)
        self.menu.append(self.current_item)

        self.power_item = Gtk.MenuItem(label="Power: --")
        self.power_item.set_sensitive(False)
        self.menu.append(self.power_item)

        # Stats section (if learning is available)
        if self.learning:
            self.menu.append(Gtk.SeparatorMenuItem())

            self.capacity_item = Gtk.MenuItem(label="Capacity: --")
            self.capacity_item.set_sensitive(False)
            self.menu.append(self.capacity_item)

            self.cycles_item = Gtk.MenuItem(label="Cycles: --")
            self.cycles_item.set_sensitive(False)
            self.menu.append(self.cycles_item)

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

            # Positive current = charging (depends on wiring)
            charging = current > 10

            # Calculate percentage using discharge curve (smoothed if available)
            if HAS_LEARNING:
                percent = smoothed_voltage_to_percent(voltage, charging)
            else:
                percent = voltage_to_percent(voltage)

            # Record sample for learning
            if self.learning:
                self.learning.record_sample(voltage, current, power)

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

            # Update time remaining
            if self.learning:
                time_str = self.learning.format_time_remaining(percent, current)
                if time_str:
                    self.time_item.set_label(f"Time: {time_str}")
                elif charging:
                    self.time_item.set_label("Time: Charging...")
                else:
                    self.time_item.set_label("Time: Calculating...")

                # Update learned stats
                stats = self.learning.get_stats()
                self.capacity_item.set_label(
                    f"Capacity: {stats['effective_capacity_mah']:.0f} mAh "
                    f"(nom: {stats['nominal_capacity_mah']})"
                )
                self.cycles_item.set_label(f"Cycles tracked: {stats['cycle_count']}")
            else:
                self.time_item.set_label("Time: N/A (no learning)")

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
