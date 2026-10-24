# ⚡ Home Assistant Peak Shaving (Norwegian Capacity Tariff / Nettleie)

A production-ready Home Assistant custom integration engineered specifically for the Norwegian electricity grid capacity tariff (**kapasitetsledd / nettleie**), with out-of-the-box presets for **Lede** (Vestfold, Telemark, Buskerud) and general Norwegian grid operators (Elvia, Tensio, Glitre, BKK).

**100% GUI Configured:** No YAML editing required! Setup, device addition, priority ranking, and tuning are managed entirely through Home Assistant's Settings UI and Lovelace dashboard.

---

## 🎯 The Problem: Norwegian Capacity Tariff (Kapasitetsledd)

In Norway, your monthly grid fee (**kapasitetsledd**) is determined by the **average of your 3 highest peak clock hours on 3 distinct days** in a calendar month:

$$P_{\text{monthly\_max}} = \frac{P_{\text{day1\_max\_hour}} + P_{\text{day2\_max\_hour}} + P_{\text{day3\_max\_hour}}}{3}$$

### Lede Capacity Tariff Tiers (Privat, inkl. mva)

| Kapasitetstrinn | Månedsmaks (kW) | Fastledd (Lede) | Konsekvens ved overskridelse |
|---|---|---|---|
| **Trinn 1** | **0 – 5 kW** | **268,75 kr/mnd** | Laveste trinn |
| **Trinn 2** | **5 – 10 kW** | **458,75 kr/mnd** | +190 kr ekstra for hele måneden |
| **Trinn 3** | **10 – 15 kW** | **647,50 kr/mnd** | +379 kr ekstra |
| **Trinn 4** | **15 – 20 kW** | **837,50 kr/mnd** | +569 kr ekstra |
| **Trinn 5** | **20 – 25 kW** | **1 027,50 kr/mnd** | +759 kr ekstra |
| **Trinn 6** | **25 – 50 kW** | **1 596,25 kr/mnd** | +1 327 kr ekstra |

> **Key takeaway:** A single heavy cooking session, water heater cycle, and EV charge coinciding for just 45 minutes can breach the 5 kW tier for that day. Triggering this on 3 days permanently locks you into a higher bill for the entire month.

---

## 🚀 Key Features

- **100% GUI-Driven (No YAML Required):**
  - Interactive **Config Flow** and **Options Flow** in Home Assistant Settings.
  - Add, configure, prioritize, and delete devices through native dialogs with entity search and filtering.
- **Norwegian Tariff Presets:**
  - One-click presets for Lede (0–5 kW, 5–10 kW, 10–15 kW, etc.) or custom limits.
  - Interactive dropdown directly on your Lovelace dashboard to change tiers on the fly (e.g., switch temporarily to 10 kW when guests arrive).
- **Predictive Trajectory Math:**
  - Evaluates remaining time in the clock hour ($T_{\text{rem}}$) and consumed energy ($E_{\text{consumed}}$).
  - Dynamically calculates the **maximum allowable power**:
    $$P_{\text{max\_allowed}} = \frac{E_{\text{target}} - E_{\text{consumed}}}{T_{\text{rem}}}$$
  - Sheds only when the projected clock-hour average is on trajectory to breach the tier limit.
- **Multi-Device Support:**
  - **Heat Pumps / ACs (`climate.*`):**
    - Comfort protection: Will **never shed** if room temperature is at or below the configurable minimum temperature floor (frost/comfort limit).
    - Intelligent shedding: Can perform **temperatures setback** (e.g., -2°C) to keep compressor and fan idling, or completely turn off.
    - Compressor anti-short-cycling protection with configurable cooldowns (e.g., 5 minutes).
  - **EV Chargers (Easee, Zaptec, Wallbox, Go-e):**
    - Multi-stage modulation: Automatically throttles charging current in steps (e.g., $16\text{A} \rightarrow 11\text{A} \rightarrow 8\text{A} \rightarrow 6\text{A}$) before pausing the charger.
    - Battery protection: Preserves emergency range—**never sheds or throttles** if battery state of charge (SoC %) is below user-defined threshold (e.g., 40%).
    - Supports both 1-phase and 3-phase connections (230V IT and 400V TN).
  - **Power Plugs / Relays (`switch.*`):**
    - Controls water heaters, floor heating, or heavy plug loads.
    - Priority-based shedding with toggle cooldown timers.
- **Strict Anti-Hunting (Hysteresis):**
  - Prevents rapid on/off oscillations. A device is only restored when spare grid headroom exceeds the device's rated draw plus a safety hysteresis margin.
- **Staggered Restoration:**
  - When headroom is restored or at the top of a new clock hour (:00:00), devices are restored sequentially with time delays to prevent simultaneous inrush spikes.
- **Full Lovelace Dashboard Card:**
  - Pre-built dashboard card with real-time gauges, status badges, tier selection dropdown, and limit sliders.

---

## 📐 Mathematical Formulation

At any given timestamp $t$ within the current clock hour $[H:00, (H+1):00)$:

1. **Elapsed & Remaining Time:**
   $$m = \text{minute} + \frac{\text{second}}{60}, \quad T_{\text{rem}} = \frac{60 - m}{60} \text{ hours}$$

2. **Effective Limit:**
   $$P_{\text{effective}} = P_{\text{target\_limit}} - P_{\text{safety\_margin}}$$
   $$E_{\text{target}} = P_{\text{effective}} \times 1.0\text{ h}$$

3. **Remaining Energy Budget:**
   $$E_{\text{remaining}} = E_{\text{target}} - E_{\text{consumed}}$$

4. **Maximum Allowable Continuous Power:**
   $$P_{\text{max\_allowed}} = \frac{E_{\text{remaining}}}{T_{\text{rem}}}$$

5. **Projected Hour Average:**
   $$P_{\text{projected}} = E_{\text{consumed}} + \left(P_{\text{grid}} \times T_{\text{rem}}\right)$$

6. **Excess Power to Shed:**
   $$\Delta P_{\text{excess}} = P_{\text{grid}} - P_{\text{max\_allowed}}$$

When $\Delta P_{\text{excess}} > 0$ and persists beyond the persistence filter (or during severe spikes), the integration iterates through registered devices in **ascending priority order** (Priority 1 sheds first, Priority 10 sheds last) until excess power is mitigated.

When $\Delta P_{\text{excess}} < -P_{\text{hysteresis}}$, the integration restores loads in **descending priority order** (Priority 10 restores first), ensuring:

$$P_{\text{headroom}} \ge P_{\text{device}} + P_{\text{hysteresis}}$$

---

## 📦 Installation

### Option 1: HACS (Recommended)
1. In Home Assistant, open **HACS** $\rightarrow$ **Integrations**.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add repository URL: `https://github.com/daniel/hassio-peakshave` with category **Integration**.
4. Click **Download**, then restart Home Assistant.

### Option 2: Manual Installation
1. Copy the `custom_components/peak_shave` folder to your Home Assistant `config/custom_components/` directory:
   ```bash
   cp -r custom_components/peak_shave /config/custom_components/
   ```
2. Restart Home Assistant.

---

## ⚙️ Configuration (Via UI)

### Step 1: Initial Setup
1. In Home Assistant, navigate to **Settings** $\rightarrow$ **Devices & Services** $\rightarrow$ **Add Integration**.
2. Search for **Peak Shaving (Nettleie)**.
3. Configure the primary grid meter:
   - **Main Grid Power Sensor:** Select your total house power sensor (e.g. `sensor.ams_active_power`, `sensor.tibber_pulse_power`, or `sensor.shelly_3em_power`). Both **W** and **kW** units are automatically detected!
   - **Hourly Energy Sensor (Optional):** If your HAN/AMS reader exposes an hourly accumulator (e.g. `sensor.ams_energy_this_hour`), select it. Otherwise, leave blank—the integration automatically performs internal numerical integration!
   - **Tariff Preset:** Select **Lede Trinn 1 (0 – 5 kW)** or your preferred tier.
   - **Safety Margin:** Set your safety buffer (default: `0.3 kW` / 300 W).

### Step 2: Adding Controllable Devices
1. In **Settings** $\rightarrow$ **Devices & Services**, locate **Peak Shaving (Nettleie)** and click **Configure**.
2. Select an action from the menu:
   - **Add Heat Pump / AC (Climate):**
     - Select entity (e.g. `climate.daikin_heatpump`).
     - Choose Action: **Temperatursenkning (Setback)** (recommended) or **Turn Off**.
     - Set **Min Temperature Floor** (e.g. 18°C) so heating is never sacrificed.
     - Set **Priority** (1–10).
   - **Add EV Charger:**
     - Select current limit entity (e.g. `number.easee_charger_circuit_limit`).
     - Select pause switch (e.g. `switch.easee_charger_is_enabled`).
     - Select battery SoC sensor (e.g. `sensor.my_car_battery_level`).
     - Set **Min Battery Reserve** (e.g. 40%). Below this SoC, the EV will never be throttled.
     - Set **Priority** (1–10).
   - **Add Smart Plug / Switch:**
     - Select switch entity (e.g. `switch.water_heater_plug`).
     - Enter estimated kW (e.g. `2.0 kW`).
     - Set **Priority** (1–10).

---

## 📊 Entities Created

| Entity | Type | Description |
|---|---|---|
| `sensor.peak_shaving_nettleie_status` | Sensor | Operational state (`normal`, `warning`, `shedding`, `limit_exceeded`) |
| `sensor.peak_shaving_nettleie_grid_power` | Sensor | Real-time active grid load in kW |
| `sensor.peak_shaving_nettleie_effective_limit` | Sensor | Active target ceiling minus safety margin (kW) |
| `sensor.peak_shaving_nettleie_hour_energy_consumed` | Sensor | Accumulated energy this clock hour (kWh) |
| `sensor.peak_shaving_nettleie_hour_budget_remaining` | Sensor | Remaining energy allowance this hour (kWh) |
| `sensor.peak_shaving_nettleie_projected_hour_average` | Sensor | Forecasted clock-hour average power (kW) |
| `sensor.peak_shaving_nettleie_max_allowable_power` | Sensor | Maximum safe power for rest of hour (kW) |
| `sensor.peak_shaving_nettleie_headroom` | Sensor | Spare power headroom (kW) |
| `sensor.peak_shaving_nettleie_active_shed_devices` | Sensor | Count and attributes of currently shed devices |
| `switch.peak_shaving_nettleie_automation_enabled` | Switch | Master toggle for peak shaving automation |
| `select.peak_shaving_nettleie_tariff_tier` | Select | Dropdown to switch Lede tiers (5kW, 10kW, etc.) |
| `number.peak_shaving_nettleie_target_limit` | Number | Dynamic kW target limit slider |
| `number.peak_shaving_nettleie_safety_margin` | Number | Dynamic kW safety buffer slider |

---

## 🖥️ Lovelace Dashboard

A ready-to-use Lovelace dashboard configuration is included in [`lovelace_card.yaml`](lovelace_card.yaml).

Simply paste the YAML into any dashboard view as a **Manual Card** for an instant real-time control center:

```yaml
# Add Manual Card -> paste contents of lovelace_card.yaml
```

---

## 🛠️ Developer Services

The integration registers native Home Assistant services:

- `peak_shave.restore_all`: Instantly restores all shed or throttled devices back to their normal operational states.
- `peak_shave.recalculate`: Forces an immediate evaluation cycle of grid loads and forecasts.

---

## 🧪 Testing

The core algorithm and device controllers are unit tested:

```bash
python3 -m unittest discover -s tests -v
```

All 12 unit tests pass covering tariff math, multi-stage EV modulation, climate setback, hysteresis anti-hunting, and rollover resets.

---

## 📄 License

MIT License. Designed and engineered for Norwegian households navigating the modern capacity tariff.
