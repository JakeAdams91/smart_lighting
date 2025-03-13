"""
SMART LIGHT CONTROLLER 
for home assistant
Copyright (c) 2025 Jacob M. Adams

Licensed under the Prosperity Public License 3.0.0
Free for personal and non-commercial use.
Commercial use requires a paid license. Contact jakeadams@duck.com for details.
Full license text at https://prosperitylicense.com or the LICENSE.md file

------------------------------------------------------
--------------------- DESCRIPTION --------------------
------------------------------------------------------
A comprehensive motion-based smart lighting system that adjusts brightness and color temperature
based on time of day, ambient light levels, and motion detection status.

Input Parameters:
- binary_sensor: Binary sensor entity to detect motion
- light: Light entity to control
- timer: Timer entity for idle timeout
- brightness_low: Minimum brightness percentage (default: 20)
- brightness_high: Maximum brightness percentage (default: 100)
- color_temp_kelvin_low: Warm color temperature in Kelvin (default: 2000)
- color_temp_kelvin_high: Cool color temperature in Kelvin (default: 4500)
- idle_timeout_day: Minutes before turning off during daytime (default: 10)
- idle_timeout_evening: Minutes before turning off during evening (default: 15)
- idle_timeout_night: Minutes before turning off during nighttime (default: 2)
- nightlight_entity: Optional separate light entity for nighttime mode
- nightlight_brightness_pct: Optional brightness for nightlight
- transition: Transition time in seconds (default: 0.75)
- lux_sensor: Optional illuminance sensor to check ambient light
- lux_min: Minimum lux threshold (default: 5)
- lux_max: Maximum lux threshold (default: 60)
- lights_for_lux_check: Light group to check if any lights are on

---------------------------------------------------------
------------------- FUNCTIONAL OVERVIEW ------------------
---------------------------------------------------------
1. Caches entity states for optimized performance
2. Performs lux-based checks to prevent unnecessary light activation
3. Calculates appropriate lighting based on time segments:
   - Morning: 1 hour before sunrise → 2 hours after sunrise
   - Day: 2 hours after sunrise → sunset
   - Evening: sunset → 2 hours after sunset
   - Twilight: 2 hours after sunset → 3 hours after sunset
   - Night: 3 hours after sunset → 1 hour before sunrise
4. Adjusts brightness and color temperature based on time segment
5. Manages motion detection and timer-based light control
6. Applies lighting changes with transition effects
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
# ----------------------------------------------------------------------
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
    twilight_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .3, 1.0)

    evening_start = local_sunset
    evening_end = evening_start + evening_offset  # e.g., ~ sunset + 2.0 (winter) or +0.5 (summer)

    twilight_start = evening_end
    twilight_end = twilight_start + twilight_offset # e.g., ~ sunset + 1.0 (winter) or +0.3 (summer)

    return {
        "morning_start": local_sunrise - 1, # just gonna hard-code mornings. 
        "morning_end":   local_sunrise + 2, # I don't want extremely bright white the first 2 hours of sunrise. 
        "day_start":     local_sunrise + 2, # so i am going to ease us all into it.
        "day_end":       local_sunset,
        "evening_start": evening_start,
        "evening_end":   evening_end,
        "twilight_start": twilight_start,
        "twilight_end":  twilight_end,
        # Night will be everything after twilight_end until morning_start
    }


def calculate_settings_by_time(light_entity,
                               current_hour: float, 
                               local_sunrise: float, 
                               local_sunset: float, 
                               idle_timeout_day: int, 
                               idle_timeout_evening: int, 
                               idle_timeout_night: int,
                               nightlight_brightness_pct: int,
                               nightlight_entity):
    """
    This version uses dynamic evening/twilight boundaries 
    computed from day length.
    """
    # Get dynamic transitions
    transitions = get_dynamic_transitions(local_sunrise, local_sunset)

    time_modes = {
        "morning": {
            "condition": lambda current_hour: transitions["morning_start"] <= current_hour < transitions["morning_end"],
            "brightness": lambda: max(BRIGHTNESS_LOW,int(BRIGHTNESS_HIGH * 0.75)),
            "color_temp": lambda: max(COLOR_TEMP_LOW,int(COLOR_TEMP_HIGH * 0.65)),
            "timeout": lambda: idle_timeout_day // 2,
            "light_entity": light_entity
        },
        "day": {
            "condition": lambda current_hour: transitions["day_start"] <= current_hour < transitions["day_end"],
            "brightness": lambda: BRIGHTNESS_HIGH,
            "color_temp": lambda: COLOR_TEMP_HIGH,
            "timeout": lambda: idle_timeout_day,
            "light_entity": light_entity
        },
        "evening": {
            "condition": lambda current_hour: transitions["evening_start"] <= current_hour < transitions["evening_end"],
            "brightness": lambda: max(BRIGHTNESS_LOW, int(BRIGHTNESS_HIGH * 0.70)),
            "color_temp": lambda: max(COLOR_TEMP_LOW,int(COLOR_TEMP_HIGH * 0.65)),
            "timeout": lambda: idle_timeout_evening,
            "light_entity": light_entity
        },
        "twilight": {
            "condition": lambda current_hour: transitions["twilight_start"] <= current_hour < transitions["twilight_end"],
            "brightness": lambda: max(BRIGHTNESS_LOW, int(BRIGHTNESS_HIGH * 0.60)),
            "color_temp": lambda: max(COLOR_TEMP_LOW,int(COLOR_TEMP_HIGH * 0.55)),
            "timeout": lambda: idle_timeout_evening // 2,
            "light_entity": light_entity
        },
        "night": {
            "condition": lambda current_hour: (current_hour >= transitions["twilight_end"] and current_hour < 24) or
                                   (current_hour >= 0 and current_hour < transitions["morning_start"]),
            "brightness": lambda: nightlight_brightness_pct if nightlight_brightness_pct else BRIGHTNESS_LOW,
            "color_temp": lambda: COLOR_TEMP_LOW,
            "timeout": lambda: idle_timeout_night,
            "light_entity": nightlight_entity if nightlight_entity else light_entity
        }
    }

    for mode, setting in time_modes.items(): # e.g., 'night' : {brightness, color_temp, idle_timeout_sec, light_entity}
        if setting["condition"](current_hour):
            return {
                "mode": mode,
                "brightness_pct": setting["brightness"](),
                "color_temp_kelvin": setting["color_temp"](),
                "idle_timeout_sec": setting["timeout"]() * 60,
                "light_entity": setting["light_entity"],
            }

# ---------------------- TURN ON/OFF LIGHT
# ----------------------------------------------
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
        
        # Skip if light is already off and we want it off
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
            
        # Prepare service data
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
lux_sensor = data.get("lux_sensor")
lux_max = data.get("lux_max", 60)
lux_value = get_lux_value(lux_sensor) # returns 0 as default.
lights_for_lux_check = data.get("lights_for_lux_check")
all_room_lights_state = hass.states.get(lights_for_lux_check).state if lights_for_lux_check is not None else None

# Check if all_room_lights_state is None (used for jobs that don't need lux evals)
# Only checks if lux > max allowed when lights are off. any light on will artificially impact the lux rating.
if all_room_lights_state is None or all_room_lights_state == "on" or (all_room_lights_state == "off" and int(lux_value) <= int(lux_max)):
    # get caller arguments
    MIN_DAYLIGHT=int(data.get("min_daylight", 9)) # higher min_daylight = longer transitions
    MAX_DAYLIGHT=int(data.get("max_daylight",14)) # shorter max_daylight = shorter transitions
    BRIGHTNESS_LOW = int(data.get("brightness_low", 20))
    BRIGHTNESS_HIGH = int(data.get("brightness_high", 100))
    COLOR_TEMP_LOW = int(data.get("color_temp_kelvin_low", 2000))
    COLOR_TEMP_HIGH = int(data.get("color_temp_kelvin_high", 4500))
    motion_source = data.get("motion_source")
    binary_sensor = data.get("binary_sensor")
    light_entity = data.get("light")
    timer_entity = data.get("timer")
    idle_timeout_day_minutes = int(data.get("idle_timeout_day", 10))
    idle_timeout_evening_minutes = int(data.get("idle_timeout_evening", 15))
    idle_timeout_night_minutes = int(data.get("idle_timeout_night", 2))
    nightlight_entity = data.get("nightlight_entity", None)
    nightlight_brightness_pct = data.get("nightlight_brightness_pct", None)
    transition = data.get("transition", 0.75)

    # Get current time & sunrise/sunset
    current_time = dt_util.now()
    current_hour = current_time.hour + (current_time.minute / 60)  # Convert to decimal hour
    local_sunrise, local_sunset = get_sun_times()
    
    calculations = calculate_settings_by_time(
                        light_entity=light_entity,
                        current_hour=current_hour, 
                        local_sunrise=local_sunrise, 
                        local_sunset=local_sunset, 
                        idle_timeout_day=idle_timeout_day_minutes, 
                        idle_timeout_evening=idle_timeout_evening_minutes, 
                        idle_timeout_night=idle_timeout_night_minutes,
                        nightlight_brightness_pct=nightlight_brightness_pct,
                        nightlight_entity=nightlight_entity
                    )

    room_motion_state = get_cached_state(binary_sensor).state if binary_sensor else "on" # default "on" for cases that don't need motion sensing. 
    idle_timer_state = get_cached_state(timer_entity).state if timer_entity else "active" # default "active" just lets the code run to turn on light. 
    
    if room_motion_state == "on":
        """
        for reference:
        calculations = {
            mode (str) 'night' or 'day' and such
            brightness_pct (int) - the brightness to set the light
            color_temp_kelvin (int) - the temperature to set the light
            idle_timeout_sec (int) - timeout in seconds
            light_entity - the light object that will be acted upon.
        }
        """
        light_entity = calculations.get("light_entity")
        brightness_pct = calculations.get("brightness_pct")
        color_temp_kelvin = calculations.get("color_temp_kelvin")
        idle_timeout_sec = calculations.get("idle_timeout_sec")

        apply_light_settings(light_entity=light_entity, brightness_pct=brightness_pct, color_temp_kelvin=color_temp_kelvin, transition=transition)
        if timer_entity is not None:
            start_idle_timer(timer_entity=timer_entity, duration_sec=idle_timeout_sec)
    else:
        if idle_timer_state in ["idle", "paused"]:
            affected_light = calculations.get("light_entity")
            apply_light_settings(light_entity=affected_light, brightness_pct=0, transition=1, color_temp_kelvin=None)

STATE_CACHE.clear()
