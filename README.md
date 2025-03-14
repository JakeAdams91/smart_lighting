# Smart Light & Nightlight Automation

This repository provides Home Assistant automation scripts for managing **smart lighting and nightlights**, allowing for motion-based, adaptive illumination while supporting manual override functionality. Designed for flexibility, these scripts can be customized to work with various smart home ecosystems.

## Features

### **1. Nightlight Control**
- **Motion-activated:** When 1 sensor detects motion, all nightlights come on at dimmed brightness.
- **Guided-lighting:** Lights boost brightness as they detect motion. return to dimmed state when clear.
- **Ambient-sensitive:** Optional - Lights only activate when illuminance is below a configurable threshold.
- **Dynamic brightness:** Adjusts brightness based on time of day.
- **Color adaptation:** Warmer hues at at nights, cooler white, midday.
- **Auto-off:** Turns off lights after a period of inactivity.
- **Customizable thresholds:** fully configurable

### **2. Smart Light Control**
- **Motion-activated:** turn on when motion is detected.
- **Ambient-sensitive:** Optional - Lights only activate when illuminance is below a configurable threshold.
- **Dynamic brightness:** Adjusts brightness based on time of day.
- **Color adaptation:** Warmer hues at nights, cooler white midday.
- **Auto-off:** Turns off lights after a period of inactivity.
- **Customizable thresholds:** fully configurable

### **3. Override Functions**
- **Manual Override:** Deactivates specified automations
- **Timed Override:** set override durations
- **Auto-Resume:** Automation resumes after the override expires, adjusting brightness smoothly.


## Getting Started
### **Prerequisites**

- Home Assistant installed and running.
- Motion sensors and smart lights integrated with Home Assistant.
- `input_select, input_boolean, and timer` helpers configured for custom illuminance thresholds.
- **Python Scripts enabled** in Home Assistant (`python_script:` must be included in `configuration.yaml`).
- **Required Helpers Created** (see Configuration section).

### **Installation**

1. **Clone the repository**:
   ```sh
   git clone https://github.com/JakeAdams91/smart_lighting.git
   cd smart-lighting-automation
   ```

2. **Enable Python Scripts in Home Assistant**:
   - Open `configuration.yaml`
   - Add the following line if not already present:
     ```yaml
     python_script:
     ```
   - Restart Home Assistant after saving the changes.

3. **Upload Python script files**:
   - Copy all `.py` files to the `python_scripts` directory in your Home Assistant configuration folder:
   ```sh
   cp python_scripts/*.py /config/python_scripts/
   ```
   - If the `python_scripts` folder does not exist, create it manually in `/config/`.

4. **Restart Home Assistant** for changes to take effect.

### **Configuration**

To properly use the automation scripts, you must define the following **helpers** in `configuration.yaml`:

#### **Input Select (For Automation Overrides)**
Each automation override requires an **input_select** entity, use 'placeholder' as the default options value. Script overwrites the options list with list of automations it deactivated, as a way to persist the list(array) into memory:
```yaml
input_select:
  override_<your_room>_automations:
    name: "Override for <Your Room> (or any other descriptive name)"
    options: 
      - placeholder
```

#### **Input Boolean (For Override Toggle)**
Each override must have an **input_boolean** to toggle manual control:
```yaml
input_boolean:
  override_<your_room>_toggle:
    name: "Override Toggle for <Your Room> (or any other descriptive name)"
```

#### **Timers (For Automations & Overrides)**
- The **Smart Light Controller** requires a **timer for each room/area** you plan to automate this lends you flexibility to say, define your kitchen to turn off after 5 minutes no activity while your game room does so in 30, and so forth.
- The **Nightlight Controller** requires **at least one timer**.
- The **Automation Override** requires **a timer for each room/area**.

Example Timer Configuration:
```yaml
timer:
  livingroom_idle_timer:
    name: "Living Room Idle Timer"
    restore: true

  kitchen_idle_timer:
    name: "Kitchen Idle Timer"
    restore: true

  override_{yourValue}_timer: # NOTE - currently hardcoded to expect override_{}_timer. 
    # I will patch to give you full naming control. but for now, the automation override variables MUST CONFORM TO NAMING STANDARD. override_{}_ ...
    name: "Descriptive name"
    restore: true
```
> **Note:** The override functionality requires the input_boolean, input_select, and timer. the smart lighting and nightlight just requires a timer. 
> **Note:** Replace `<your_room>` with the actual room name in your setup. Each automated area should have its own `input_text`, `input_boolean`, and `timer`. 

## How It Works

### **Smart Light Controller**

1. If **motion is detected** and **ambient illuminance is below the threshold**, the light turns on.
2. The brightness dynamically scales based on time of day.
3. The color temp (warm ambers - cool whites) adjusts based on time of day.
4. Lights auto-shut off after no motion detected for specified time.
5. You can set a specific light to come on at night as a night light.

### **Nightlight Activation**

1. If **motion is detected** and **ambient illuminance is below the threshold**, the light turns on.
2. The brightness dynamically scales based on time of day.
3. The color temp (warm ambers - cool whites) adjusts based on time of day.
4. After the sensor clears, light returns to dimmed setting
5. Lights auto-shut off after no motion detected for specified time.

### **Override Functionality**

- **Manual override:** Allows users to turn lights on/off without automation interference.
- **Timed override:** Temporarily disables automation for a predefined duration.
- **Auto-resume:** After the override period ends, automation re-enables and adjusts lighting accordingly.

## Customization

- Modify automation triggers to include additional sensors or conditions.
- configure your automations adjusting passed in params. 



# ☕ Support My Work
Optional - but highly appreciated

[![CashApp](https://img.shields.io/badge/CashApp-%24JakeAdams-green?style=for-the-badge)](https://cash.app/$artchecks)
[![Venmo](https://img.shields.io/badge/Venmo-@jakeAdams32-blue?style=for-the-badge)](https://venmo.com/jacob-adams-32)

## License
This project is licensed under the Prosperity Public License 3.0.0 License. See `LICENSE` for details.

