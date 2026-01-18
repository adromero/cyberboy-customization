#!/usr/bin/env python3
"""
Battery Learning Module - Hybrid SOC using coulomb counting + voltage calibration.
Tracks discharge patterns and estimates time remaining.
Learns from actual usage to improve accuracy over time.
"""

import json
import os
import time
import csv
import subprocess
from pathlib import Path
from collections import deque
from threading import Lock
from datetime import datetime

# Data storage location
DATA_DIR = Path.home() / ".local" / "share" / "cyberboy-battery"
HISTORY_FILE = DATA_DIR / "discharge_history.json"
LEARNED_FILE = DATA_DIR / "learned_data.json"
CSV_LOG_DIR = DATA_DIR / "logs"

# Battery configuration
NOMINAL_CAPACITY_MAH = 3400  # 3x Samsung 18650 3400mAh in series
SHUNT_OHMS = 0.01  # Waveshare UPS 3S uses 0.01 ohm shunt resistor
I2C_ADDRESS = 0x41
I2C_BUS = 1

# INA219 register addresses
INA219_REG_SHUNT_VOLTAGE = 0x01
INA219_REG_BUS_VOLTAGE = 0x02

# INA219 shunt voltage LSB = 10µV
# With 0.01Ω shunt: current (mA) = shunt_raw * 10µV / 0.01Ω = shunt_raw * 1.0 mA
SHUNT_LSB_UV = 10


class INA219DirectReader:
    """
    Read INA219 registers directly, calculating current from shunt voltage.
    No calibration register needed - works after any power cycle.
    """

    def __init__(self, address=I2C_ADDRESS, busnum=I2C_BUS):
        from smbus2 import SMBus
        self._bus = SMBus(busnum)
        self._address = address

    def _read_register(self, reg):
        """Read a 16-bit register and swap bytes (INA219 is big-endian)."""
        raw = self._bus.read_word_data(self._address, reg)
        return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)

    def _read_signed_register(self, reg):
        """Read a signed 16-bit register."""
        val = self._read_register(reg)
        if val > 32767:
            val -= 65536
        return val

    def voltage(self):
        """Read bus voltage in volts."""
        raw = self._read_register(INA219_REG_BUS_VOLTAGE)
        # Shift right 3 bits, LSB = 4mV
        return (raw >> 3) * 0.004

    def current(self):
        """Read current in mA from shunt voltage (no calibration needed)."""
        raw = self._read_signed_register(INA219_REG_SHUNT_VOLTAGE)
        # shunt_uV = raw * 10, current_mA = shunt_uV / (shunt_ohms * 1000)
        # With 0.01Ω: current_mA = raw * 10 / 10 = raw
        return raw * SHUNT_LSB_UV / (SHUNT_OHMS * 1000)

    def power(self):
        """Read power in mW."""
        return self.voltage() * abs(self.current())

    def close(self):
        """Close the I2C bus."""
        try:
            self._bus.close()
        except Exception:
            pass


# Singleton INA219 reader instance
_ina219_reader = None
_ina219_reader_lock = Lock()


def get_ina219_reader():
    """Get the singleton INA219DirectReader instance."""
    global _ina219_reader
    with _ina219_reader_lock:
        if _ina219_reader is None:
            _ina219_reader = INA219DirectReader()
        return _ina219_reader


# Corrected 3S Li-ion discharge curve (voltage -> percent)
# More data points in the flat middle region for better accuracy
DISCHARGE_CURVE = [
    (12.60, 100),
    (12.50, 95),
    (12.40, 90),
    (12.30, 85),
    (12.20, 80),
    (12.00, 75),
    (11.90, 70),
    (11.80, 65),
    (11.70, 60),
    (11.60, 55),
    (11.50, 50),
    (11.40, 45),
    (11.30, 40),
    (11.20, 35),
    (11.10, 30),
    (11.00, 25),
    (10.80, 20),
    (10.60, 15),
    (10.40, 10),
    (10.20, 7),
    (10.00, 5),
    (9.80, 3),
    (9.60, 2),
    (9.40, 1),
    (9.00, 0),
]

# Voltage thresholds
VOLT_MIN = 9.0
VOLT_MAX = 12.6

# Warning thresholds
LOW_VOLTAGE_WARN = 10.2  # ~7%
CRITICAL_VOLTAGE = 9.6   # ~2%

# Notification thresholds (percent)
WARN_THRESHOLDS = [20, 10, 5]
CRITICAL_THRESHOLD = 5

# Charging detection
CHARGE_CURRENT_THRESHOLD = 10  # mA - above this = charging
CHARGE_VOLTAGE_SETTLED_TIME = 30  # seconds after unplug before trusting voltage
POST_UNPLUG_GRACE_PERIOD = 300  # 5 minutes before blending toward voltage SOC

# Load compensation for voltage sag under load
# Estimated internal resistance for 3S pack (~170mΩ per cell × 3 + wiring)
INTERNAL_RESISTANCE_OHMS = 0.5

# Sleep/suspend detection - if gap between samples exceeds this, assume sleep occurred
MAX_SAMPLE_INTERVAL_SECONDS = 30


def load_compensated_voltage(measured_voltage, current_ma):
    """
    Compensate voltage for load-induced sag.
    Returns estimated open-circuit voltage (OCV).
    """
    # Negative current = discharging, positive = charging
    if current_ma < 0:  # Discharging
        # V_ocv = V_measured + I × R
        compensation = (abs(current_ma) / 1000.0) * INTERNAL_RESISTANCE_OHMS
        return measured_voltage + compensation
    return measured_voltage


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


def percent_to_voltage(percent):
    """Convert percentage to expected voltage (for calibration)."""
    if percent >= 100:
        return DISCHARGE_CURVE[0][0]
    if percent <= 0:
        return DISCHARGE_CURVE[-1][0]

    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if p_low <= percent <= p_high:
            ratio = (percent - p_low) / (p_high - p_low)
            return v_low + ratio * (v_high - v_low)
    return VOLT_MIN


class BatteryLearning:
    """
    Hybrid SOC estimation using coulomb counting with voltage calibration.
    - Uses coulomb counting for smooth, accurate tracking during operation
    - Uses voltage to calibrate/reset SOC at known points (full charge, empty)
    - Learns actual capacity from discharge cycles
    """

    def __init__(self):
        self._lock = Lock()
        self._ensure_data_dir()

        # Recent samples for averaging (last 60 samples = ~5 min at 5s intervals)
        self._recent_current = deque(maxlen=60)
        self._recent_power = deque(maxlen=60)

        # Hybrid SOC tracking
        self._coulomb_soc = None  # Coulomb-counted SOC (0-100)
        self._voltage_soc = None  # Voltage-based SOC for reference
        self._last_sample_time = None
        self._last_voltage = None
        self._last_current = None

        # Charge state tracking
        self._is_charging = False
        self._charge_state_changed_time = time.time() - 60  # Start as "settled"
        self._voltage_settled = True  # Assume settled on startup
        self._last_charge_time = time.time() - POST_UNPLUG_GRACE_PERIOD  # Allow blending on boot

        # Notification tracking (don't repeat warnings)
        self._warnings_sent = set()
        self._last_warning_time = 0

        # Session tracking for capacity learning
        self._session_start_time = time.time()
        self._session_start_soc = None
        self._session_discharge_mah = 0.0

        # CSV logging
        self._csv_file = None
        self._csv_writer = None
        self._init_csv_logging()

        # Load learned data
        self._learned = self._load_learned_data()

        # Initialize coulomb SOC from learned data if available
        if self._learned.get("last_soc") is not None:
            self._coulomb_soc = self._learned["last_soc"]

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CSV_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _init_csv_logging(self):
        """Initialize CSV logging for the current session."""
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            csv_path = CSV_LOG_DIR / f"battery_{date_str}.csv"
            file_exists = csv_path.exists()

            self._csv_file = open(csv_path, "a", newline="")
            self._csv_writer = csv.writer(self._csv_file)

            if not file_exists:
                self._csv_writer.writerow([
                    "timestamp", "voltage", "current_ma", "power_mw",
                    "voltage_soc", "coulomb_soc", "hybrid_soc",
                    "charging", "capacity_mah"
                ])
                self._csv_file.flush()
        except Exception as e:
            print(f"CSV logging init error: {e}")
            self._csv_writer = None

    def _log_csv(self, voltage, current, power, v_soc, c_soc, h_soc, charging):
        """Log a sample to CSV."""
        if self._csv_writer:
            try:
                self._csv_writer.writerow([
                    datetime.now().isoformat(),
                    f"{voltage:.3f}",
                    f"{current:.1f}",
                    f"{power:.1f}",
                    f"{v_soc:.1f}",
                    f"{c_soc:.1f}" if c_soc is not None else "",
                    f"{h_soc:.1f}",
                    "1" if charging else "0",
                    f"{self._learned['effective_capacity_mah']:.0f}"
                ])
                self._csv_file.flush()
            except Exception:
                pass

    def _load_learned_data(self):
        """Load learned capacity and patterns from disk."""
        default = {
            "effective_capacity_mah": NOMINAL_CAPACITY_MAH,
            "cycle_count": 0,
            "total_discharge_mah": 0,
            "avg_power_mw": 9000,  # ~9W typical for Pi 5 + screen
            "typical_draw_ma": 850,
            "last_full_charge_time": None,
            "capacity_samples": [],
            "last_soc": None,  # Persist SOC across restarts
            "last_soc_time": None,
        }
        try:
            if LEARNED_FILE.exists():
                with open(LEARNED_FILE, "r") as f:
                    data = json.load(f)
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
            # Save current SOC for persistence
            if self._coulomb_soc is not None:
                self._learned["last_soc"] = self._coulomb_soc
                self._learned["last_soc_time"] = time.time()

            with open(LEARNED_FILE, "w") as f:
                json.dump(self._learned, f, indent=2)
        except Exception:
            pass

    def _send_notification(self, title, message, urgency="normal"):
        """Send a notification via mako/notify-send."""
        try:
            # Use notify-send which works with mako
            cmd = ["notify-send", "-u", urgency, title, message]
            subprocess.run(cmd, timeout=5, capture_output=True)
        except Exception:
            pass

    def _check_warnings(self, percent, charging):
        """Check if we need to send low battery warnings."""
        if charging:
            # Clear warnings when charging so they can trigger again
            self._warnings_sent.clear()
            return

        now = time.time()

        # Don't spam notifications (min 60s between any warnings)
        if now - self._last_warning_time < 60:
            return

        for threshold in WARN_THRESHOLDS:
            if percent <= threshold and threshold not in self._warnings_sent:
                self._warnings_sent.add(threshold)
                self._last_warning_time = now

                if threshold <= CRITICAL_THRESHOLD:
                    self._send_notification(
                        "CRITICAL BATTERY",
                        f"Battery at {percent:.0f}%! Shutdown imminent.",
                        urgency="critical"
                    )
                elif threshold <= 10:
                    self._send_notification(
                        "Low Battery",
                        f"Battery at {percent:.0f}%. Please connect charger.",
                        urgency="critical"
                    )
                else:
                    self._send_notification(
                        "Battery Warning",
                        f"Battery at {percent:.0f}%.",
                        urgency="normal"
                    )
                break  # Only send one notification per check

    def record_sample(self, voltage, current_ma, power_mw):
        """
        Record a battery sample and update hybrid SOC.
        Returns the current hybrid SOC percentage.
        """
        with self._lock:
            now = time.time()

            # Determine charge state
            was_charging = self._is_charging
            self._is_charging = current_ma > CHARGE_CURRENT_THRESHOLD

            # Track charge state changes for voltage settling
            if was_charging != self._is_charging:
                self._charge_state_changed_time = now
                self._voltage_settled = False
            elif self._charge_state_changed_time:
                if now - self._charge_state_changed_time > CHARGE_VOLTAGE_SETTLED_TIME:
                    self._voltage_settled = True

            # Track when we were last charging (for grace period after unplug)
            if self._is_charging:
                self._last_charge_time = now

            # Calculate voltage-based SOC
            self._voltage_soc = voltage_to_percent(voltage)

            # Track current and power for averaging
            self._recent_current.append(abs(current_ma))
            self._recent_power.append(power_mw)

            # Update average power
            if self._recent_power:
                self._learned["avg_power_mw"] = sum(self._recent_power) / len(self._recent_power)

            # === HYBRID SOC CALCULATION ===

            # Initialize coulomb SOC if needed
            if self._coulomb_soc is None:
                self._coulomb_soc = self._voltage_soc
                self._session_start_soc = self._coulomb_soc

            # Coulomb counting: integrate current over time
            if self._last_sample_time is not None:
                dt_seconds = now - self._last_sample_time

                # Sleep/suspend detection: if time gap is too large, assume we slept
                # and reset to voltage SOC instead of calculating phantom discharge
                if dt_seconds > MAX_SAMPLE_INTERVAL_SECONDS:
                    # Sleep detected - reset coulomb SOC to voltage SOC
                    # We don't know what happened during sleep, so trust voltage
                    self._coulomb_soc = self._voltage_soc
                    # Don't do coulomb counting for this sample
                else:
                    # Normal operation - do coulomb counting
                    dt_hours = dt_seconds / 3600.0
                    capacity = self._learned["effective_capacity_mah"]

                    if self._is_charging:
                        # Charging: add charge (positive current)
                        charge_mah = abs(current_ma) * dt_hours
                        delta_soc = (charge_mah / capacity) * 100.0
                        self._coulomb_soc = min(100.0, self._coulomb_soc + delta_soc)
                    else:
                        # Discharging: subtract charge (negative current)
                        discharge_mah = abs(current_ma) * dt_hours
                        delta_soc = (discharge_mah / capacity) * 100.0
                        self._coulomb_soc = max(0.0, self._coulomb_soc - delta_soc)

                        # Track discharge for capacity learning
                        self._session_discharge_mah += discharge_mah
                        self._learned["total_discharge_mah"] += discharge_mah

            # === VOLTAGE CALIBRATION POINTS ===

            # Calibrate at full charge using load-compensated voltage
            # This accounts for voltage sag under typical load
            compensated_v = load_compensated_voltage(voltage, current_ma)
            if (compensated_v >= 12.35 and  # Lower threshold to account for load
                abs(current_ma) < 150 and   # Allow slightly higher current
                self._voltage_settled and
                not self._is_charging):
                # Battery is full and settled - set to 100%
                if self._coulomb_soc < 95:
                    # Learn from this cycle
                    self._on_full_charge()
                self._coulomb_soc = 100.0

            # Calibrate at empty (voltage at critical level)
            # Only trust this if voltage is in a plausible range (> 5V)
            # A reading below 5V indicates hardware glitch or disconnected UPS,
            # not an actual empty battery (3S Li-ion minimum is ~9V)
            if voltage > 5.0 and voltage <= CRITICAL_VOLTAGE and not self._is_charging:
                self._coulomb_soc = max(0.0, self._voltage_soc)

            # Gradual drift correction: slowly blend toward voltage SOC
            # This prevents long-term coulomb counting drift
            # Only blend if we've been off charger for 5+ minutes (grace period)
            # Also require plausible voltage (> 5V) to avoid blending toward bogus 0% readings
            time_since_charge = now - self._last_charge_time
            if (voltage > 5.0 and
                self._voltage_settled and
                not self._is_charging and
                time_since_charge > POST_UNPLUG_GRACE_PERIOD):
                # Blend 0.2% toward voltage SOC per sample (gentler than before)
                blend_factor = 0.002
                self._coulomb_soc = (
                    self._coulomb_soc * (1 - blend_factor) +
                    self._voltage_soc * blend_factor
                )

            # While charging and voltage not settled, don't trust voltage SOC
            # Just use coulomb counting
            if self._is_charging or not self._voltage_settled:
                # Clamp coulomb SOC to reasonable bounds based on voltage
                # Don't show > 95% unless voltage confirms it
                if voltage < 12.2:
                    self._coulomb_soc = min(self._coulomb_soc, 90.0)
                if voltage < 12.0:
                    self._coulomb_soc = min(self._coulomb_soc, 80.0)

            # Update tracking
            self._last_sample_time = now
            self._last_voltage = voltage
            self._last_current = current_ma

            # Get hybrid SOC (coulomb-based with voltage calibration)
            hybrid_soc = max(0.0, min(100.0, self._coulomb_soc))

            # Check for low battery warnings
            self._check_warnings(hybrid_soc, self._is_charging)

            # Log to CSV
            self._log_csv(voltage, current_ma, power_mw,
                         self._voltage_soc, self._coulomb_soc, hybrid_soc,
                         self._is_charging)

            # Periodically save
            if int(now) % 30 == 0:
                self._save_learned_data()

            return hybrid_soc

    def _on_full_charge(self):
        """Called when battery reaches full charge - learn from this cycle."""
        if self._session_discharge_mah > 500:  # Meaningful discharge (>500mAh)
            if self._session_start_soc and self._session_start_soc > 20:
                # Calculate effective capacity from this cycle
                soc_used = self._session_start_soc
                observed_capacity = (self._session_discharge_mah / (soc_used / 100.0))

                # Sanity check (should be in reasonable range)
                if 1000 < observed_capacity < 5000:
                    self._learned["capacity_samples"].append(observed_capacity)
                    self._learned["capacity_samples"] = self._learned["capacity_samples"][-10:]

                    # Update effective capacity (weighted average, recent samples weighted more)
                    if self._learned["capacity_samples"]:
                        weights = [1 + i * 0.2 for i in range(len(self._learned["capacity_samples"]))]
                        weighted_sum = sum(c * w for c, w in zip(self._learned["capacity_samples"], weights))
                        self._learned["effective_capacity_mah"] = weighted_sum / sum(weights)

            self._learned["cycle_count"] += 1
            self._learned["last_full_charge_time"] = time.time()
            self._save_learned_data()

        # Reset session tracking
        self._session_discharge_mah = 0.0
        self._session_start_soc = 100.0

    def get_hybrid_soc(self):
        """Get the current hybrid SOC."""
        with self._lock:
            if self._coulomb_soc is not None:
                return max(0.0, min(100.0, self._coulomb_soc))
            return self._voltage_soc or 0.0

    def get_time_remaining(self, percent, current_ma):
        """
        Estimate time remaining based on current draw and learned capacity.
        Returns (hours, minutes) tuple or None if cannot estimate.
        """
        with self._lock:
            if self._is_charging:
                return None

            # Use average current if we have samples
            if self._recent_current and len(self._recent_current) >= 3:
                avg_current = sum(self._recent_current) / len(self._recent_current)
            else:
                avg_current = abs(current_ma)

            # Need meaningful discharge current
            if avg_current < 30:
                return None

            # Calculate remaining capacity
            effective_capacity = self._learned["effective_capacity_mah"]
            remaining_mah = (percent / 100.0) * effective_capacity

            # Time = capacity / current
            hours_remaining = remaining_mah / avg_current

            # Sanity check
            if hours_remaining < 0 or hours_remaining > 50:
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
            if not self._is_charging:
                return None

            # Use average current
            if self._recent_current and len(self._recent_current) >= 3:
                avg_current = sum(self._recent_current) / len(self._recent_current)
            else:
                avg_current = abs(current_ma)

            if avg_current < 30:
                return None

            # Calculate capacity needed
            effective_capacity = self._learned["effective_capacity_mah"]
            needed_mah = ((100.0 - percent) / 100.0) * effective_capacity

            # Time = capacity / current
            hours_to_full = needed_mah / avg_current

            if hours_to_full < 0 or hours_to_full > 50:
                return None

            hours = int(hours_to_full)
            minutes = int((hours_to_full - hours) * 60)

            return (hours, minutes)

    def format_time_remaining(self, percent, current_ma):
        """Get formatted string for time remaining/to full."""
        if self._is_charging:
            result = self.get_time_to_full(percent, current_ma)
            if result:
                h, m = result
                if h > 0:
                    return f"{h}h {m}m to full"
                return f"{m}m to full"
            return "Charging..."
        else:
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
                "voltage_soc": self._voltage_soc,
                "coulomb_soc": self._coulomb_soc,
            }

    def is_charging(self):
        """Return current charging state."""
        return self._is_charging

    def get_voltage_soc(self):
        """Get voltage-based SOC for comparison."""
        return self._voltage_soc

    def close(self):
        """Clean up resources."""
        self._save_learned_data()
        if self._csv_file:
            try:
                self._csv_file.close()
            except Exception:
                pass


# Voltage smoothing for display stability
class VoltageSmoothing:
    """Exponential moving average filter for voltage to prevent jumps."""

    def __init__(self, alpha=0.15):
        self._alpha = alpha
        self._smoothed_voltage = None
        self._last_charging = None

    def smooth(self, voltage, charging):
        """Apply EMA smoothing, with faster response on charge state change."""
        if self._smoothed_voltage is None:
            self._smoothed_voltage = voltage
            self._last_charging = charging
            return voltage

        # Use faster response when charge state changes
        if self._last_charging != charging:
            alpha = min(0.5, self._alpha * 3)
        else:
            alpha = self._alpha

        self._smoothed_voltage = alpha * voltage + (1 - alpha) * self._smoothed_voltage
        self._last_charging = charging

        return self._smoothed_voltage

    def reset(self):
        self._smoothed_voltage = None


# Singleton instances
_voltage_smoother = VoltageSmoothing(alpha=0.15)
_battery_learning = None
_battery_learning_lock = Lock()


def get_battery_learning():
    """Get the singleton BatteryLearning instance."""
    global _battery_learning
    with _battery_learning_lock:
        if _battery_learning is None:
            _battery_learning = BatteryLearning()
        return _battery_learning


def get_smoothed_voltage(raw_voltage, charging):
    """Get smoothed voltage using global EMA filter."""
    return _voltage_smoother.smooth(raw_voltage, charging)


def smoothed_voltage_to_percent(raw_voltage, charging):
    """
    Convert raw voltage to percentage with smoothing applied.
    NOTE: This is deprecated - use get_battery_learning().record_sample() instead
    for hybrid SOC that uses coulomb counting.
    """
    smoothed = get_smoothed_voltage(raw_voltage, charging)
    return voltage_to_percent(smoothed)


def get_hybrid_soc(voltage, current, power):
    """
    Get hybrid SOC using coulomb counting + voltage calibration.
    This is the recommended function for getting battery percentage.
    """
    bl = get_battery_learning()
    return bl.record_sample(voltage, current, power)
