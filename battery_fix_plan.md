# Battery Monitoring Fix Plan

## Problem Summary

The battery percentage drops rapidly from 100% to ~65% immediately after unplugging from the charger, then discharges normally from there. This is a software calibration issue, not a hardware problem.

## Root Causes

### 1. Discharge Curve Based on Open-Circuit Voltage (OCV)
The current discharge curve assumes voltage readings at rest (no load):
```python
DISCHARGE_CURVE = [
    (12.60, 100),
    (12.00, 75),   # ← Problem: 12.0V under load ≠ 75%
    ...
]
```

**Reality:** A fully charged 3S Li-ion (12.6V OCV) will read ~12.0-12.2V under your typical 50-100mA load due to internal resistance. The curve incorrectly interprets this as 75%.

### 2. Voltage Settling Time Too Short
```python
CHARGE_VOLTAGE_SETTLED_TIME = 30  # seconds
```

After unplugging, surface charge dissipates over 30-60 seconds. Once "settled" at 30s, the code trusts the (now lower) voltage and starts blending toward it.

### 3. Aggressive Drift Correction
```python
blend_factor = 0.01  # 1% blend per sample toward voltage SOC
```

At ~5 second sample intervals, this accumulates quickly:
- 60 samples/5 min × 1% blend = significant drift toward incorrect voltage SOC

### 4. Full-Charge Calibration Threshold Too High
```python
if voltage >= 12.25 and ...  # Only calibrates to 100% if voltage >= 12.25V
```

After unplugging and under load, voltage drops below 12.25V within seconds, so the 100% calibration never triggers.

---

## Proposed Fixes

### Fix 1: Load-Compensated Voltage Calculation
Add internal resistance compensation to voltage readings before SOC lookup.

```python
# Estimated internal resistance for 3S pack
# Note: Start with 0.5Ω and tune based on observed voltage sag
# To calibrate: measure voltage drop when load changes, R = ΔV / ΔI
INTERNAL_RESISTANCE_OHMS = 0.5  # ~170mΩ per cell × 3 (accounts for wiring too)

def load_compensated_voltage(measured_voltage, current_ma):
    """Compensate voltage for load-induced sag."""
    # Note: Verify current sign convention matches your INA219 wiring
    # Common: negative = discharging, positive = charging
    if current_ma < 0:  # Discharging
        # V_ocv = V_measured + I × R
        compensation = (abs(current_ma) / 1000.0) * INTERNAL_RESISTANCE_OHMS
        return measured_voltage + compensation
    return measured_voltage
```

### Fix 2: Extended Post-Unplug Grace Period
Add a longer grace period after unplugging before trusting voltage SOC.

```python
CHARGE_VOLTAGE_SETTLED_TIME = 30      # Keep for basic settling
POST_UNPLUG_GRACE_PERIOD = 300        # 5 minutes before blending toward voltage SOC
```

In `__init__`, initialize the tracking variable:
```python
self._last_charge_time = time.time() - POST_UNPLUG_GRACE_PERIOD  # Allow blending immediately on boot
```

Track when charging stopped and don't blend during grace period:
```python
if self._is_charging:
    self._last_charge_time = now

# Only blend if we've been off charger for 5+ minutes
time_since_charge = now - self._last_charge_time
if self._voltage_settled and not self._is_charging and time_since_charge > POST_UNPLUG_GRACE_PERIOD:
    # Safe to blend toward voltage SOC
```

### Fix 3: Reduce Blend Aggressiveness
```python
blend_factor = 0.002  # 0.2% per sample instead of 1%
```

This slows drift correction to ~1% per minute instead of ~1% per 5 seconds.

### Fix 4: Lower Full-Charge Calibration Threshold
```python
# Calibrate at full charge - use load-compensated voltage
# With 0.5Ω IR and 100mA load: compensation = 50mV
# Raw 12.25V + 50mV = 12.30V compensated, so threshold must be <= 12.35V
compensated_v = load_compensated_voltage(voltage, current_ma)
if (compensated_v >= 12.35 and  # Lower threshold to account for typical load
    abs(current_ma) < 150 and   # Allow slightly higher current
    self._voltage_settled and
    not self._is_charging):
    self._coulomb_soc = 100.0
```

### Fix 5: Adjust Discharge Curve for Typical Load
Alternative to load compensation - use a curve calibrated for ~75mA load:

```python
# Curve adjusted for ~75mA typical load (adds ~11mV per cell sag)
DISCHARGE_CURVE_UNDER_LOAD = [
    (12.55, 100),  # Was 12.60
    (12.45, 95),   # Was 12.50
    (12.35, 90),   # Was 12.40
    (12.25, 85),   # Was 12.30
    (12.15, 80),   # Was 12.20
    (11.95, 75),   # Was 12.00
    # ... rest similar
]
```

---

## Implementation Order

1. **Fix 1 (Load Compensation)** - Most impactful, addresses root cause
2. **Fix 2 (Grace Period)** - Prevents premature drift after unplugging
3. **Fix 3 (Reduce Blend)** - Makes drift correction gentler
4. **Fix 4 (Calibration Threshold)** - Ensures 100% calibration works

Fix 5 is an alternative to Fix 1 if load compensation proves unreliable.

---

## Testing Plan

1. Start with battery on charger at 100%
2. Unplug and observe:
   - Voltage should show ~12.0-12.2V (normal under load)
   - SOC should stay at 95-100% for first 5 minutes
   - SOC should then slowly track voltage over next 30+ minutes
3. Discharge for 1 hour and verify:
   - SOC drops ~3-5% per hour at idle (not 30% in first few minutes)
   - Voltage and SOC track reasonably together

---

## Files to Modify

- `$HOME/customization/battery_learning.py`

---

## Rollback

Keep backup before changes:
```bash
cp $HOME/customization/battery_learning.py $HOME/customization/battery_learning.py.bak
```

Reset learned data if needed:
```bash
rm ~/.local/share/cyberboy-battery/learned_data.json
```
