# Smart Light & Nightlight Automation

This repository provides Home Assistant automation scripts for managing **smart lighting and nightlights**, allowing for motion-based, adaptive illumination while supporting manual override functionality. Designed for flexibility, these scripts can be customized to work with various smart home ecosystems.

## Features

### **1. Nightlight Control**
- **Motion-activated:** all nightlights come one at dimmed brightness when any 1 detects motion.
- **Guided-lighting:** Lights brighten as they detect motion. return to dimmed state when clear.
- **Ambient-sensitive:** Optional - Lights only activate when illuminance is below a configurable threshold.
- **Dynamic brightness:** Adjusts brightness based on time of day.
- **Color adaptation:** Warmer hues at at nights, cooler white midday.
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
- helpers configured. (timers, booleans, etc.)
- Python Scripts enabled in Home Assistant (`python_script:` must be included in `configuration.yaml`).

### **Installation**

1. **Clone the repository**:
   ```sh
   git clone https://github.com/JakeAdams91/smart_lighting.git
   cd smart_lighting
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

- Open **Home Assistant UI** → **Settings** → **Automations & Scripts**.
- Locate the imported scripts.
- Create Automations

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

## Roadmap

- **Scene integration:** Sync lighting with Home Assistant scenes.
- **Time-based adjustments:** Modify brightness and color temperature based on time of day.
- **Voice assistant support:** Enable Alexa/Google Assistant control for automation overrides.

## Contributing

Contributions are welcome! If you'd like to improve the automations, feel free to fork the repository and submit a pull request.

### **To contribute:**

1. Fork the repository.
2. Create a new branch (`feature-branch-name`).
3. Make changes and commit them.
4. Push to your fork and open a pull request.

## License
This project is licensed under the Prosperity Public License 3.0.0 License. See `LICENSE` for details.
