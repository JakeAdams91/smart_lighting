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
        return 0
        
    sensor_state = get_cached_state(sensor_entity)
    if not sensor_state or sensor_state.state in ('unknown', 'unavailable', 'None'):
        return 0
        
    try:
        lux_value = float(sensor_state.state)
        return lux_value
    except (ValueError, TypeError):
        return 0


def is_motion_active(binary_sensor):
    """Safely check if motion is detected."""
    if not binary_sensor:
        return False
        
    motion_state = get_cached_state(binary_sensor)
    if not motion_state:
        return False
        
    if motion_state.state in ('unavailable', 'unknown'):
        return False
        
    return motion_state.state == "on"

# ----------------- IDLE TIMER HANDLING
# ----------------------------------------------
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
        return
        
    timer_state = hass.states.get(timer_entity)
    if not timer_state:
        logger.warning(f"Timer entity {timer_entity} not found")
        return
        
    current_state = timer_state.state
    duration = seconds_to_hms(duration_sec)
    
    if current_state in ["active", "paused"]:
        hass.services.call("timer", "cancel", {"entity_id": timer_entity})
        
    hass.services.call("timer", "start", {"entity_id": timer_entity, "duration": duration})


# ----------------- GET SUNRISE/SUNSET TIME AS DECIMAL 12.50 == 12:30 
# -----------------------------------------------------------------------
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
            return sunrise_float, sunset_float
    return 7.0, 18.0  # Fallback sunrise/sunset times.


# ----------------- CALC THE BRIGHTNESS/ COLOR TEMP BY TIME OF DAY.
# -----------------------------------------------------------------------
def scale_offset(daylight_hours:float, 
                 min_daylight=9, max_daylight=14,
                 min_offset=.3, max_offset=2):
    """
    Returns a dynamic offset (in hours) between [min_offset, max_offset],
    depending on how short/long the day is.
    
    - If daylight_hours is near min_daylight (e.g. 10 hrs), 
      this returns around max_offset (e.g. ~2.5 hrs).
    - If daylight_hours is near max_daylight (e.g. 14 hrs),
      this returns around min_offset (e.g. ~1.0 hr).
    
    Adjust the min_daylight, max_daylight, min_offset, max_offset 
    values as desired for your location/latitude.
    """
    day_hours = max(min_daylight, min(daylight_hours, max_daylight))
    ratio = (day_hours - min_daylight) / (max_daylight - min_daylight)
    # We invert (1 - ratio) so that short days = bigger offsets, long days = smaller offsets
    return min_offset + (max_offset - min_offset) * (1 - ratio)


def get_dynamic_transitions(local_sunrise:float, local_sunset:float):
    """
    Returns a dict of dynamic time boundaries for Evening, Twilight, etc.
    All times are in 'decimal hour' format (e.g., 19.5 = 7:30 PM).
    """
    daylight_hours = local_sunset - local_sunrise

    # sets range, 0.5 - 2hrs for evening, 0.3 - 1hr for twilight
    evening_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .5, 2.0)
    twilight_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .5, 1.0)

    morning_start = local_sunrise - twilight_offset
    morning_end = local_sunrise + twilight_offset
    evening_start = local_sunset
    evening_end = evening_start + evening_offset  # e.g., ~ sunset + 2.0 (winter) or +0.5 (summer)

    twilight_start = evening_end
    twilight_end = twilight_start + twilight_offset # e.g., ~ sunset + 1.0 (winter) or +0.3 (summer)


    return {
        "morning_start": morning_start,
        "morning_end":   morning_end,
        "day_start":     morning_end, # daystart is morning end.
        "day_end":       local_sunset,
        "evening_start": evening_start,
        "evening_end":   evening_end,
        "twilight_start": twilight_start,
        "twilight_end":  twilight_end,
        # Night will be everything after twilight_end until morning_start
    }

def calculate_settings_by_time(current_hour, local_sunrise, local_sunset, brightness_low, brightness_boost, color_temp_high, color_temp_low):
    """
    Determines brightness and color temperature dynamically based on time of day.
    """
    transitions = get_dynamic_transitions(local_sunrise, local_sunset)
    
    time_modes = {
        "morning": {
            "condition": lambda current_hour: transitions["morning_start"] <= current_hour < transitions["morning_end"],
            "brightness": lambda: min(100, brightness_low + 10),
            "boosted_pct": lambda: min(100, brightness_boost - 10),
            "color_temp": lambda: int(color_temp_high * 0.65),
        },
        "day": {
            "condition": lambda current_hour: transitions["day_start"] <= current_hour < transitions["day_end"],
            "brightness": lambda: min(100, brightness_low + 40),
            "boosted_pct": lambda: brightness_boost,
            "color_temp": lambda: color_temp_high,
        },
        "evening": {
            "condition": lambda current_hour: transitions["evening_start"] <= current_hour < transitions["evening_end"],
            "brightness": lambda: min(100, brightness_low + 10),
            "boosted_pct": lambda: min(100, brightness_boost - 10),
            "color_temp": lambda: int(color_temp_high * 0.70),
        },
        "twilight": {
            "condition": lambda current_hour: transitions["twilight_start"] <= current_hour < transitions["twilight_end"],
            "brightness": lambda: min(100, brightness_low + 5),
            "boosted_pct": lambda: min(100, brightness_boost - 20),
            "color_temp": lambda: int(color_temp_high * 0.65),
        },
        "night": {
            "condition": lambda current_hour: (current_hour >= transitions["twilight_end"] and current_hour < 24) or
                            (current_hour >= 0 and current_hour < transitions["morning_start"]),
            "brightness": lambda: brightness_low,
            "boosted_pct": lambda: min(100, brightness_boost - 25),
            "color_temp": lambda: color_temp_low,
        },
    }

    for mode_name, setting in time_modes.items():
        if setting["condition"](current_hour):
            return {
                "mode": mode_name,
                "brightness_pct": (brightness_pct := setting["brightness"]()),
                "color_temp_kelvin": setting["color_temp"](),
                "boosted_pct":max(brightness_pct, setting["boosted_pct"]())
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
        else:
            if current_state == "on":
                hass.services.call("light", "turn_off", service_data)
                
        return True
    except Exception as e:
        logger.error(f"Error applying light settings to {light_entity}: {str(e)}")
        return False

# --------------------- MAIN LOGIC EXECUTION
# ----------------------------------------------
# Get parameters from data
MIN_DAYLIGHT=int(data.get("min_daylight", 9))
MAX_DAYLIGHT=int(data.get("max_daylight",14))
motion_source = data.get("motion_source")
nightlights = data.get("nightlights", None)
light_entity = data.get("light")
timer_entity = data.get("timer")
lux_sensor = data.get("lux_sensor")
lux_threshold = int(data.get("lux_threshold", 19))
brightness_low = int(data.get("brightness_low", 10))
brightness_high = int(data.get("brightness_high", 100))
color_temp_low = int(data.get("color_temp_kelvin_low", 2000))
color_temp_high = int(data.get("color_temp_kelvin_high", 3500))
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

any_motion_active = False

if nightlights is not None:
    # First pass: Check if ANY motion is active at all
    # This ensures we always have at least dim lights on anywhere if motion is detected
    if not forced_dim:  # Only do this check when we're not in forced_dim mode
        for nightlight in nightlights:
            binary_sensor = nightlight.get("binary_sensor")
            if is_motion_active(binary_sensor):
                any_motion_active = True
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
            apply_light_settings(light_entity=light_entity, brightness_pct=0, color_temp_kelvin=settings["color_temp_kelvin"], transition=transition)
            continue
        
        # Handle motion state for this specific nightlight
        motion_active = is_motion_active(binary_sensor)

        # If we're in forced_dim mode, we only want to dim the specific light that triggered the automation
        if forced_dim:
            # Only dim this specific light if it's the one that triggered the motion_cleared event
            if motion_source == binary_sensor:
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings['brightness_pct'], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
        else:
            # Normal motion processing mode:
            # 1. Boost lights with active motion
            # 2. Ensure all other lights are at least dimmed if any motion is active anywhere
            if motion_active:
                # This light's motion sensor is active, boost it
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["boosted_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            elif any_motion_active:
                # There's motion elsewhere in the house, so this light should be at least dimmed
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            else:
                # No motion anywhere, set to default brightness
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )

# Process single light if no nightlights list
else:
    if not light_entity:
        logger.error("No light entity provided")
    else:
        stop_processing = False
        # Check ambient light if sensor provided
        if lux_sensor:
            lux_value = get_lux_value(lux_sensor)
            if lux_value >= lux_threshold:
                # Too bright, turn off light
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
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["boosted_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )
            else:
                # Dim the light (motion cleared)
                apply_light_settings(
                    light_entity=light_entity, 
                    brightness_pct=settings["brightness_pct"], 
                    color_temp_kelvin=settings["color_temp_kelvin"], 
                    transition=transition
                )

# Start idle timer if provided
if timer_entity:
    start_idle_timer(timer_entity, idle_timeout_sec)

STATE_CACHE.clear()