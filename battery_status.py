#!/usr/bin/env python3
"""
Battery status helper for conky - outputs battery info with time remaining
"""

import sys

try:
    from ina219 import INA219
except ImportError:
    print("> N/A")
    sys.exit(0)

# Import shared module if available
try:
    from battery_learning import (
        get_battery_learning, voltage_to_percent,
        SHUNT_OHMS, I2C_ADDRESS, I2C_BUS
    )
    HAS_LEARNING = True
except ImportError:
    HAS_LEARNING = False
    SHUNT_OHMS = 0.1
    I2C_ADDRESS = 0x41
    I2C_BUS = 1

    # Corrected 3S Li-ion discharge curve
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

try:
    ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
    ina.configure()
    voltage = ina.voltage()
    current = ina.current()
    percent = voltage_to_percent(voltage)
    charging = current > 10

    # Status indicator
    status = " CHG" if charging else ""

    # Get time remaining if learning module available
    time_str = ""
    if HAS_LEARNING:
        bl = get_battery_learning()
        power = ina.power()
        bl.record_sample(voltage, current, power)
        time_str = bl.format_time_remaining(percent, current)

    # Output formatted for conky (execpi interprets ${color} codes)
    print(f"> {percent:.0f}%{status}")
    if time_str:
        print(f"${{color4}}  {time_str}")

except Exception as e:
    print("> ERR")
