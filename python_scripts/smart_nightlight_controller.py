"""
SMART NIGHTLIGHT CONTROLLER 
for home assistant
Copyright (c) 2025 Jacob M. Adams

Licensed under the Prosperity Public License 3.0.0
Free for personal and non-commercial use.
Commercial use requires a paid license. Contact jakeadams@duck.com for details.
Full license text at https://prosperitylicense.com or the LICENSE.md file

------------------------------------------------------
--------------------- DESCRIPTION --------------------
------------------------------------------------------
An advanced nightlight control system that manages multiple lights throughout the home,
coordinating brightness levels based on motion detection, time of day, and ambient light.

Input Parameters:
- motion_source: The motion sensor that triggered this automation
- nightlights: List of nightlight configurations, each containing:
  * light: Light entity to control
  * binary_sensor: Binary sensor for motion detection
  * lux_sensor: Illuminance sensor for ambient light detection
  * lux_threshold: Optional custom lux threshold
- light: Single light entity (when not using nightlights list)
- timer: Timer entity for idle timeout
- lux_sensor: Global illuminance sensor
- lux_threshold: Global lux threshold (default: 19)
- brightness_low: Minimum brightness percentage (default: 10)
- brightness_high: Maximum brightness percentage (default: 100)
- color_temp_kelvin_low: Warm color temperature (default: 2000)
- color_temp_kelvin_high: Cool color temperature (default: 3500)
- transition: Transition time in seconds (default: 0.75)
- idle_timeout_mins: Minutes before turning off lights (default: 2)
- forced_dim: Flag to force dimming instead of boosting (default: False)

---------------------------------------------------------
------------------- FUNCTIONAL OVERVIEW ------------------
---------------------------------------------------------
1. Provides coordinated control of multiple nightlights throughout a space
2. Two operational modes:
   - Multiple nightlights: Manages a network of lights with motion detection
   - Single light: Controls a single light entity
3. Implements smart motion response:
   - Boosts brightness for lights with active motion
   - Maintains dim lighting in areas without direct motion when motion exists elsewhere
   - Dims or turns off lights based on ambient light levels and motion status
4. Adjusts settings based on time of day:
   - Morning: Gentler lighting with warmer color temperature
   - Day: Brighter lighting with cooler color temperature
   - Evening: Moderately bright with warmer tones
   - Twilight: Dimmer lighting with warmer color temperature
   - Night: Dimmest setting with warmest light color
"""

### Helper Functions ###
# ------------------------ HELPER FUNCTIONS ----------------- 
# ----------------- ENTITY CACHING | STATE MANAGEMENT -------
STATE_CACHE = {}
def get_cached_state(entity_id):
    """load entity state to cache or fetch it if not available."""
    if entity_id not in STATE_CACHE:
        STATE_CACHE[entity_id] = hass.states.get(entity_id)
    return STATE_CACHE[entity_id]

def refresh_state_cache(entity_ids=None):
    """Refresh the state cache for specific entities or clear it entirely."""
    if entity_ids is None:
        STATE_CACHE.clear()
    else:
        for entity_id in entity_ids:
            if entity_id in STATE_CACHE:
                STATE_CACHE[entity_id] = hass.states.get(entity_id)


def get_lux_value(sensor_entity):
    """Retrieve lux value from a illuminance sensor."""
    if not sensor_entity:
        logger.debug("No lux sensor specified")
        return 0
        
    sensor_state = get_cached_state(sensor_entity)
    if not sensor_state or sensor_state.state in ('unknown', 'unavailable', 'None'):
        logger.debug(f"Lux sensor {sensor_entity} unavailable or in invalid state: {sensor_state.state if sensor_state else 'None'}")
        return 0
        
    try:
        lux_value = float(sensor_state.state)
        return lux_value
    except (ValueError, TypeError):
        logger.debug(f"Could not convert lux value '{sensor_state.state}' to number")
        return 0


def is_motion_active(binary_sensor):
    """Safely check if motion is detected."""
    if not binary_sensor:
        return False
        
    motion_state = get_cached_state(binary_sensor)
    if not motion_state:
        logger.debug(f"Motion sensor {binary_sensor} not found")
        return False
        
    if motion_state.state in ('unavailable', 'unknown'):
        logger.debug(f"Motion sensor {binary_sensor} is {motion_state.state}")
        return False
        
    return motion_state.state == "on"

# ----------------- IDLE TIMER HANDLING
def seconds_to_hms(seconds):
    """Convert seconds to a properly formatted time string 'HH:MM:SS'."""
    seconds = 0 if seconds < 0 else seconds
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

    
def start_idle_timer(timer_entity, duration_sec):
    """
    Start or restart an idle timeout timer. 
    Checks current state and restarts if necessary.
    """
    if not timer_entity:
        logger.info("No timer entity specified, skipping timer")
        return
        
    timer_state = hass.states.get(timer_entity)
    if not timer_state:
        logger.warning(f"Timer entity {timer_entity} not found")
        return
        
    current_state = timer_state.state
    duration = seconds_to_hms(duration_sec)
    
    if current_state in ["active", "paused"]:
        logger.info(f"Cancelling active timer {timer_entity} before restart")
        hass.services.call("timer", "cancel", {"entity_id": timer_entity})
        
    hass.services.call("timer", "start", {"entity_id": timer_entity, "duration": duration})
    logger.info(f"Timer {timer_entity} (re)started for {duration}")


# ----------------- GET SUNRISE/SUNSET TIME AS DECIMAL 12.50 == 12:30 
def get_sun_times():
    """Get today's sunrise and sunset times in local time."""
    sun_state = get_cached_state("sun.sun")
    if sun_state:
        utc_sunrise = sun_state.attributes.get("next_rising")
        utc_sunset = sun_state.attributes.get("next_setting")
        if utc_sunrise and utc_sunset:
            sunrise_dt = dt_util.as_local(dt_util.parse_datetime(utc_sunrise))
            sunset_dt = dt_util.as_local(dt_util.parse_datetime(utc_sunset))

            sunrise_float = sunrise_dt.hour + (sunrise_dt.minute / 60)  # Convert to decimal hour
            sunset_float = sunset_dt.hour + (sunset_dt.minute / 60)

            logger.info(f"Sunrise: {sunrise_float:.2f} | Sunset: {sunset_float:.2f}")
            return sunrise_float, sunset_float
    return 7.0, 18.0  # Fallback sunrise/sunset times.


# ----------------- CALC THE BRIGHTNESS/ COLOR TEMP BY TIME OF DAY.
def calculate_settings_by_time(current_hour, local_sunrise, local_sunset, brightness_low, brightness_boost, color_temp_high, color_temp_low):
    """
    Determines brightness and color temperature dynamically based on time of day.
    """
    time_modes = {
        "morning": {
            "condition": lambda h: local_sunrise - 1 <= h < local_sunrise + 2,
            "brightness": lambda: min(100, brightness_low + 10),
            "boosted_pct": lambda: min(100, brightness_boost - 10),
            "color_temp": lambda: int(color_temp_high * 0.65),
        },
        "day": {
            "condition": lambda h: local_sunrise + 2 <= h < local_sunset,
            "brightness": lambda: min(100, brightness_low + 40),
            "boosted_pct": lambda: brightness_boost,
            "color_temp": lambda: color_temp_high,
        },
        "evening": {
            "condition": lambda h: local_sunset <= h < local_sunset + 2,
            "brightness": lambda: min(100, brightness_low + 10),
            "boosted_pct": lambda: min(100, brightness_boost - 10),
            "color_temp": lambda: int(color_temp_high * 0.70),
        },
        "twilight": {
            "condition": lambda h: local_sunset + 2 <= h < local_sunset + 3,
            "brightness": lambda: min(100, brightness_low + 5),
            "boosted_pct": lambda: min(100, brightness_boost - 20),
            "color_temp": lambda: int(color_temp_high * 0.65),
        },
        "night": {
            "condition": lambda h: (local_sunset + 3 <= h < 24) or (0 <= h < local_sunrise - 1),
            "brightness": lambda: brightness_low,
            "boosted_pct": lambda: min(100, brightness_boost - 25),
            "color_temp": lambda: color_temp_low,
        },
    }

    for mode_name, mode_config in time_modes.items():
        if mode_config["condition"](current_hour):
            brightness_pct = mode_config["brightness"]()
            boosted_pct = mode_config["boosted_pct"]()
            return {
                "mode": mode_name,
                "brightness_pct": brightness_pct,
                "color_temp_kelvin": mode_config["color_temp"](),
                "boosted_pct":max(brightness_pct, boosted_pct)
            }

# ---------------------- TURN ON/OFF LIGHT
def apply_light_settings(light_entity, brightness_pct, color_temp_kelvin, transition):
    """
    Apply light settings

    Params:
        light_entity (hass light obj) - the light to manipulate
        brightness_pct (int) - brightness setting
        color_temp_kelvin (int) - color temp setting
        transition (int) - time in seconds for light to transition states
    Description:
        checks if the light entity exists, checks if the update is needed. 
        if brightness is only set to change 3% it'll skip
        color temp updates if any change occurred.
    """
    if not light_entity:
        logger.warning("No light entity specified")
        return False
        
    light_state = get_cached_state(light_entity)
    if not light_state:
        logger.warning(f"Light entity {light_entity} not found")
        return False
        
    try:
        current_state = light_state.state
        if current_state == "off" and brightness_pct == 0:
            return True
            
        current_attrs = light_state.attributes
        current_brightness = current_attrs.get("brightness", None)
        current_color_temp = current_attrs.get("color_temp_kelvin", None)
        
        try:
            current_brightness_pct = int(current_brightness / 2.55) if current_brightness is not None else 0
        except (TypeError, ValueError):
            current_brightness_pct = 0    
        try:
            current_color_temp_val = int(current_color_temp) if current_color_temp is not None else -1
        except (TypeError, ValueError):
            current_color_temp_val = -1
            
        # Check if changes are needed
        brightness_changed = abs(current_brightness_pct - brightness_pct) >= 3 # 3% brightness tolerance
        color_temp_changed = abs(current_color_temp_val - color_temp_kelvin) > 0 # 0 kelvin tolerance
        
        if not (brightness_changed or color_temp_changed):
            return True
            
        service_data = {"entity_id": light_entity, "transition": transition}
        
        if brightness_pct > 0:
            if brightness_changed:
                service_data["brightness_pct"] = brightness_pct
            if color_temp_changed and color_temp_kelvin is not None:
                service_data["color_temp_kelvin"] = color_temp_kelvin
                
            if brightness_changed or color_temp_changed:
                hass.services.call("light", "turn_on", service_data)
                logger.info(f"Updated {light_entity}: {brightness_pct}% brightness, {color_temp_kelvin}K")
        else:
            if current_state == "on":
                hass.services.call("light", "turn_off", service_data)
                logger.info(f"Turned OFF {light_entity}")
                
        return True
    except Exception as e:
        logger.error(f"Error applying light settings to {light_entity}: {str(e)}")
        return False

### Main Logic Execution  ###
# Get parameters from data
motion_source = data.get("motion_source")
nightlights = data.get("nightlights", None)
light_entity = data.get("light")
timer_entity = data.get("timer")
lux_sensor = data.get("lux_sensor")
lux_threshold = data.get("lux_threshold", 19)
brightness_low = data.get("brightness_low", 10)  
brightness_high = data.get("brightness_high", 100)
color_temp_low = data.get("color_temp_kelvin_low", 2000)
color_temp_high = data.get("color_temp_kelvin_high", 3500)
transition = data.get("transition", 0.75)
idle_timeout_mins = data.get("idle_timeout_mins", 2)
forced_dim = data.get("forced_dim", False)

# Current time calculations
current_time = dt_util.now()
current_hour = current_time.hour + (current_time.minute / 60)
local_sunrise, local_sunset = get_sun_times()
idle_timeout_sec = int(idle_timeout_mins)*60

# Calculate time-based settings
settings = calculate_settings_by_time(
    current_hour=current_hour,
    local_sunrise=local_sunrise,
    local_sunset=local_sunset,
    brightness_low=brightness_low,
    brightness_boost=brightness_high,
    color_temp_high=color_temp_high,
    color_temp_low=color_temp_low
)
logger.info(f"Time mode: {settings['mode']}, Brightness: {settings['brightness_pct']}%, Boosted: {settings['boosted_pct']}%")

any_motion_active = False

if nightlights is not None:
    logger.info(f"Processing {len(nightlights)} nightlights")
    
    # First pass: Check if ANY motion is active at all
    # This ensures we always have at least dim lights on anywhere if motion is detected
    if not forced_dim:  # Only do this check when we're not in forced_dim mode
        for nightlight in nightlights:
            binary_sensor = nightlight.get("binary_sensor")
            if is_motion_active(binary_sensor):
                any_motion_active = True
                logger.info(f"Motion active in the house (sensor: {binary_sensor})")
                break
    
    # Second pass: Process each light
    for nightlight in nightlights:
        light_entity = nightlight.get("light")
        binary_sensor = nightlight.get("binary_sensor")
        lux_sensor = nightlight.get("lux_sensor")
        lux_threshold = nightlight.get("lux_threshold", lux_threshold)
        
        # Check if we have all required data
        if not all([light_entity, binary_sensor, lux_sensor]):
            logger.warning(f"Missing required data for nightlight: {light_entity}")
            continue
        
        # Check ambient light level
        lux_value = get_lux_value(lux_sensor)
        if lux_value >= lux_threshold:
            # Too bright, turn off light
            logger.info(f"Lux level {lux_value} above threshold {lux_threshold} for {light_entity}, turning off")
            apply_light_settings(light_entity=light_entity, brightness_pct=0, color_temp_kelvin=settings["color_temp_kelvin"], transition=transition)
            continue
        
        # Handle motion state for this specific nightlight
        motion_active = is_motion_active(binary_sensor)

        # If we're in forced_dim mode, we only want to dim the specific light that triggered the automation
        if forced_dim:
            # Only dim this specific light if it's the one that triggered the motion_cleared event
            if motion_source == binary_sensor:
                logger.info(f"Motion cleared for {light_entity}, dimming to {settings['brightness_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings['brightness_pct'], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            # Otherwise leave this light in its current state
            else:
                logger.info(f"Skipping {light_entity} - not the light that triggered motion cleared event")
        else:
            # Normal motion processing mode:
            # 1. Boost lights with active motion
            # 2. Ensure all other lights are at least dimmed if any motion is active anywhere
            if motion_active:
                # This light's motion sensor is active, boost it
                logger.info(f"Motion active for {light_entity}, boosting to {settings['boosted_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["boosted_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            elif any_motion_active:
                # There's motion elsewhere in the house, so this light should be at least dimmed
                logger.info(f"Motion elsewhere in house, ensuring {light_entity} is dimmed to {settings['brightness_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            else:
                # No motion anywhere, set to default brightness
                logger.info(f"No motion anywhere, setting {light_entity} to {settings['brightness_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )

# Process single light if no nightlights list
else:
    logger.info("Processing single light mode")
    if not light_entity:
        logger.error("No light entity provided")
    else:
        stop_processing = False
        # Check ambient light if sensor provided
        if lux_sensor:
            lux_value = get_lux_value(lux_sensor)
            if lux_value >= lux_threshold:
                # Too bright, turn off light
                logger.info(f"Lux level {lux_value} above threshold {lux_threshold}, turning off {light_entity}")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=0, 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
                # Exit early
                if timer_entity:
                    start_idle_timer(timer_entity, idle_timeout_sec)
                stop_processing = True
        
        # If the calling automation is for motion detection (not forced dim)
        if not stop_processing:
            if not forced_dim:
                logger.info(f"Motion detected, setting {light_entity} to boosted brightness {settings['boosted_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["boosted_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            else:
                # Dim the light (motion cleared)
                logger.info(f"Motion cleared, dimming {light_entity} to {settings['brightness_pct']}%")
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )

# Start idle timer if provided
if timer_entity:
    start_idle_timer(timer_entity, idle_timeout_sec)
    
logger.info(f"Nightlight control complete for {motion_source if motion_source else 'all lights'}")

STATE_CACHE.clear()