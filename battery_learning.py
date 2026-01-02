#!/usr/bin/env python3
"""
Battery Learning Module - Tracks discharge patterns and estimates time remaining.
Learns from actual usage to improve accuracy over time.
"""

import json
import os
import time
from pathlib import Path
from collections import deque
from threading import Lock

# Data storage location
DATA_DIR = Path.home() / ".local" / "share" / "cyberboy-battery"
HISTORY_FILE = DATA_DIR / "discharge_history.json"
LEARNED_FILE = DATA_DIR / "learned_data.json"

# Battery configuration
NOMINAL_CAPACITY_MAH = 3400  # 3x Samsung 18650 3400mAh in series
SHUNT_OHMS = 0.1
I2C_ADDRESS = 0x41
I2C_BUS = 1

# Corrected 3S Li-ion discharge curve (voltage -> percent)
DISCHARGE_CURVE = [
    (12.6, 100),
    (12.4, 92),
    (12.0, 78),
    (11.7, 62),
    (11.4, 50),
    (11.1, 40),  # nominal voltage
    (10.8, 28),
    (10.5, 18),
    (10.2, 10),
    (9.9, 5),
    (9.6, 2),
    (9.0, 0),
]

# Minimum voltage (safety cutoff)
VOLT_MIN = 9.0
VOLT_MAX = 12.6

# Thresholds
LOW_VOLTAGE_WARN = 10.2
CRITICAL_VOLTAGE = 9.6


def voltage_to_percent(voltage):
    """Convert voltage to percentage using Li-ion discharge curve."""
    if voltage >= DISCHARGE_CURVE[0][0]:
        return 100.0
    if voltage <= DISCHARGE_CURVE[-1][0]:
        return 0.0

    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if v_low <= voltage <= v_high:
            ratio = (voltage - v_low) / (v_high - v_low)
            return p_low + ratio * (p_high - p_low)
    return 0.0


class BatteryLearning:
    """Tracks battery usage and learns actual capacity from discharge cycles."""

    def __init__(self):
        self._lock = Lock()
        self._ensure_data_dir()

        # Recent samples for averaging (last 60 samples = ~5 min at 5s intervals)
        self._recent_current = deque(maxlen=60)
        self._recent_power = deque(maxlen=60)

        # Session tracking
        self._session_start = time.time()
        self._session_start_percent = None
        self._last_sample_time = None
        self._last_percent = None

        # Accumulated discharge this session (mAh)
        self._session_discharge_mah = 0.0

        # Load learned data
        self._learned = self._load_learned_data()

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load_learned_data(self):
        """Load learned capacity and patterns from disk."""
        default = {
            "effective_capacity_mah": NOMINAL_CAPACITY_MAH,
            "cycle_count": 0,
            "total_discharge_mah": 0,
            "avg_power_mw": 9000,  # ~9W typical for Pi 5 + screen
            "typical_draw_ma": 850,  # Typical current draw (for 4hr runtime)
            "last_full_charge_time": None,
            "capacity_samples": [],  # List of observed capacities
        }
        try:
            if LEARNED_FILE.exists():
                with open(LEARNED_FILE, "r") as f:
                    data = json.load(f)
                    # Merge with defaults for any missing keys
                    for key in default:
                        if key not in data:
                            data[key] = default[key]
                    return data
        except Exception:
            pass
        return default

    def _save_learned_data(self):
        """Save learned data to disk."""
        try:
            with open(LEARNED_FILE, "w") as f:
                json.dump(self._learned, f, indent=2)
        except Exception:
            pass

    def record_sample(self, voltage, current_ma, power_mw):
        """Record a battery sample for learning."""
        with self._lock:
            now = time.time()
            percent = voltage_to_percent(voltage)

            # Track current and power for averaging
            self._recent_current.append(abs(current_ma))
            self._recent_power.append(power_mw)

            # Initialize session start percent
            if self._session_start_percent is None:
                self._session_start_percent = percent
                self._last_percent = percent
                self._last_sample_time = now
                return

            # Calculate discharge since last sample
            if self._last_sample_time and current_ma < -10:  # Discharging
                dt_hours = (now - self._last_sample_time) / 3600.0
                discharge_mah = abs(current_ma) * dt_hours
                self._session_discharge_mah += discharge_mah
                self._learned["total_discharge_mah"] += discharge_mah

            # Detect full charge (voltage near max and charging stopped/reversed)
            if voltage >= 12.4 and current_ma > 10:
                # Battery is charging near full
                pass
            elif voltage >= 12.5 and self._last_percent and self._last_percent < 95:
                # Just reached full charge - record cycle data
                self._on_full_charge(percent)

            # Update running average power
            if self._recent_power:
                self._learned["avg_power_mw"] = sum(self._recent_power) / len(self._recent_power)

            self._last_sample_time = now
            self._last_percent = percent

            # Periodically save
            if int(now) % 60 == 0:
                self._save_learned_data()

    def _on_full_charge(self, percent):
        """Called when battery reaches full charge - learn from this cycle."""
        if self._session_discharge_mah > 100:  # Meaningful discharge
            # Calculate effective capacity from this cycle
            percent_discharged = self._session_start_percent - 0  # Assuming we track to empty
            if self._session_start_percent and self._session_start_percent > 20:
                # Extrapolate to full capacity
                observed_capacity = (self._session_discharge_mah /
                                   (self._session_start_percent / 100.0))

                # Add to samples (keep last 10)
                self._learned["capacity_samples"].append(observed_capacity)
                self._learned["capacity_samples"] = self._learned["capacity_samples"][-10:]

                # Update effective capacity (weighted average)
                if self._learned["capacity_samples"]:
                    self._learned["effective_capacity_mah"] = (
                        sum(self._learned["capacity_samples"]) /
                        len(self._learned["capacity_samples"])
                    )

            self._learned["cycle_count"] += 1
            self._learned["last_full_charge_time"] = time.time()
            self._save_learned_data()

        # Reset session tracking
        self._session_discharge_mah = 0.0
        self._session_start_percent = percent

    def get_time_remaining(self, percent, current_ma):
        """
        Estimate time remaining based on current draw and learned capacity.
        Returns (hours, minutes) tuple or None if cannot estimate.
        """
        with self._lock:
            # Use average current if we have samples, otherwise use instantaneous
            if self._recent_current and len(self._recent_current) >= 3:
                measured_avg = sum(self._recent_current) / len(self._recent_current)
            else:
                measured_avg = abs(current_ma)

            # Use the higher of measured current or typical draw
            # This prevents overly optimistic estimates during idle
            typical = self._learned.get("typical_draw_ma", 850)
            avg_current = max(measured_avg, typical * 0.5)  # At least 50% of typical

            # Need meaningful discharge current
            if avg_current < 50:  # Less than 50mA, probably charging or idle
                return None

            # Calculate remaining capacity
            effective_capacity = self._learned["effective_capacity_mah"]
            remaining_mah = (percent / 100.0) * effective_capacity

            # Time = capacity / current
            hours_remaining = remaining_mah / avg_current

            # Sanity check (0 to 100 hours - Pi 5 at low load can run a long time)
            if hours_remaining < 0 or hours_remaining > 100:
                return None

            hours = int(hours_remaining)
            minutes = int((hours_remaining - hours) * 60)

            return (hours, minutes)

    def get_time_to_full(self, percent, current_ma):
        """
        Estimate time to full charge.
        Returns (hours, minutes) tuple or None if not charging.
        """
        with self._lock:
            if current_ma <= 10:  # Not charging
                return None

            # Use average current if available
            if self._recent_current and len(self._recent_current) >= 3:
                avg_current = sum(self._recent_current) / len(self._recent_current)
            else:
                avg_current = current_ma

            if avg_current < 50:
                return None

            # Calculate capacity needed
            effective_capacity = self._learned["effective_capacity_mah"]
            needed_mah = ((100.0 - percent) / 100.0) * effective_capacity

            # Time = capacity / current (charging slows near full, so estimate is optimistic)
            hours_to_full = needed_mah / avg_current

            if hours_to_full < 0 or hours_to_full > 100:
                return None

            hours = int(hours_to_full)
            minutes = int((hours_to_full - hours) * 60)

            return (hours, minutes)

    def format_time_remaining(self, percent, current_ma):
        """Get formatted string for time remaining/to full."""
        if current_ma > 10:  # Charging
            result = self.get_time_to_full(percent, current_ma)
            if result:
                h, m = result
                if h > 0:
                    return f"{h}h {m}m to full"
                return f"{m}m to full"
            return "Charging..."
        else:  # Discharging
            result = self.get_time_remaining(percent, abs(current_ma))
            if result:
                h, m = result
                if h > 0:
                    return f"{h}h {m}m remaining"
                return f"{m}m remaining"
            return ""

    def get_stats(self):
        """Get learned statistics."""
        with self._lock:
            return {
                "effective_capacity_mah": self._learned["effective_capacity_mah"],
                "cycle_count": self._learned["cycle_count"],
                "avg_power_mw": self._learned["avg_power_mw"],
                "nominal_capacity_mah": NOMINAL_CAPACITY_MAH,
            }


# Singleton instance
_battery_learning = None
_battery_learning_lock = Lock()


def get_battery_learning():
    """Get the singleton BatteryLearning instance."""
    global _battery_learning
    with _battery_learning_lock:
        if _battery_learning is None:
            _battery_learning = BatteryLearning()
        return _battery_learning
