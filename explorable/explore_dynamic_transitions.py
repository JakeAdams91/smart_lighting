import logging 
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

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
	morning_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .75, 1.0)
	evening_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .5, 2.75)
	twilight_offset = scale_offset(daylight_hours, MIN_DAYLIGHT, MAX_DAYLIGHT, .5, 2.0)

	if daylight_hours > 14:
		morning_start = local_sunrise
		morning_end = local_sunrise + 2
		evening_start = local_sunset - 1
	else: 
		morning_start = local_sunrise - morning_offset
		morning_end = local_sunrise + morning_offset
		evening_start = local_sunset
	
		
	evening_end = local_sunset + evening_offset # e.g., ~ sunset + 1.0 (winter) or +0.3 (summer)
	twilight_end = evening_end + twilight_offset # e.g., ~ sunset + 1.0 (winter) or +0.3 (summer)


	return {
		"morning_start": morning_start,
		"morning_end":   morning_end,
		"day_start":     morning_end,
		"day_end":       evening_start,
		"evening_start": evening_start,
		"evening_end":   evening_end,
		"twilight_start": evening_end,
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


def decimal_to_time(decimal_hour):
	hours = int(decimal_hour)
	minutes = int((decimal_hour - hours) * 60)
	seconds = int(((decimal_hour - hours) * 60 - minutes) * 60)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def convert_stringtime_to_decimaltime(local_sunrise:str, local_sunset:str):
	rise_split=local_sunrise.split(':')
	set_split = local_sunset.split(':')
	rise_hour = int(rise_split[0])
	rise_minute = int(rise_split[1])
	set_hour = int(set_split[0])
	set_minute = int(set_split[1])

	# Convert to decimal hour
	sunrise_float = rise_hour + (rise_minute / 60)  
	sunset_float = set_hour + (set_minute / 60)
	return sunrise_float, sunset_float

# these are configurable via automation call - 
# min_daylight = n 
# max_daylight = n 
# ( see automation example or review code directly /python_scripts/smart_light_controller.py )
MIN_DAYLIGHT = 9 
MAX_DAYLIGHT = 14
if __name__ == "__main__":
	"""PLAYGROUND - ADJUST VARIABLES TO SEE HOW IT IMPACTS TRANSITIONS USE TO FINE TUNE YOUR LIGHTING"""
	import json
	
	logging.info(f"{'-'*35}")
	logging.info(dict(msg="processing"))
	
	
	sun_data = [ # ADJUST HERE TO YOUR LOCALE AND TIMES; HELPS VISUALIZE THE TRANSITIONS
		("07:55","16:19", "december 21 2025; seattle"), 
		("07:25", "19:12", "march 13 2025; seattle"),
		("6:19", "19:59", "april 15 2025; seattle"),
		("05:53", "20:19", "april 29 2025; seattle"),
		("05:44", "20:28", "may 4 2025; seattle"),
		("05:36", "20:35", "may 10 2025; seattle"),
		("05:10", "21:11", "june 21 2025; seattle")
		]
	
	for local_sunrise, local_sunset, msg in sun_data:
		logging.info("{}".format(msg))
		logging.info(f"{local_sunrise=}")
		logging.info(f"{local_sunset=}")
		light_entity={'name':"hellokitty"}
		current_hour = 19.35 
		idle_timeout_day = 5 
		idle_timeout_evening=7 
		idle_timeout_night=2
		nightlight_brightness_pct=10
		nightlight_entity={'name':"hellokittyII"}
		try:
			sunrise_float, sunset_float = convert_stringtime_to_decimaltime(local_sunrise, local_sunset)
			logging.info(dict(hours_of_daylight=(sunset_float-sunrise_float)))
			# logging.info(dict(sunrise_float=sunrise_float))
			# logging.info(dict(sunset_float=sunset_float))
		except Exception as ex:
			logging.error('failed to convert time to decimal. received: local_sunrise={}, local_sunset={}. Expected format: "HH:mm"'.format(local_sunrise, local_sunset))

		transitions = None
		try:
			transitions = get_dynamic_transitions(local_sunrise=sunrise_float, local_sunset=sunset_float)
			# logging.info(json.dumps(transitions, indent=4))
		except Exception as ex:
			logging.error("failed to calculate transitions! {}".format(ex))

		try:
			converted_times = {key: decimal_to_time(value) for key, value in transitions.items()}
			logging.info(json.dumps(converted_times, indent=4))
			
		except Exception as ex:
			if transitions is not None:
				logging.error(dict(transitions_raw=transitions))
			logging.error("failed to format transitions to human readable format. {}".format(ex))
	logging.info(dict(msg="success"))

    
    
    
