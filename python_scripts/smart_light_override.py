"""
SMART LIGHT OVERRIDE SYSTEM
for home assistant
Copyright (c) 2025 Jacob M. Adams

Licensed under the Prosperity Public License 3.0.0
Free for personal and non-commercial use.
Commercial use requires a paid license. Contact jakeadams@duck.com for details.
Full license text at https://prosperitylicense.com or the LICENSE.md file

------------------------------------------------------
--------------------- DESCRIPTION --------------------
------------------------------------------------------
A flexible control mechanism that allows users to temporarily disable automation behaviors
and manually adjust lighting settings for a predefined period.

Input Parameters:
- override_id: Identifier for this override instance (defaults to "default") e.g., "livingroom"
- automation_ids: List of automation entities to disable e.g., ['automation.turn_on_livingroom', 'automation.turn_off_livingroom']
- scenes: Optional List of scene entities to activate instead of individual light settings e.g.,  ['scene.nighttheme', 'scene.moviemode']
- lights: Optional List of light entities with desired settings e.g., [{brightness_pct, brightness, color_temp_kelvin, rgb_color}, {}]
- duration: Optional duration for auto-restore (format: "HH:MM:SS")
- is_activating: int 0 or 1 Bool indicates whether we're to override or restore

requirements:
You must create an input_select, and timer entities in configuration.yaml

they MUST following naming convention:
timer:
    timer.override_{override_id}_timer

input_select:    
    input_select.override_{override_id}_automations
"""


# ------------------------ HELPER FUNCTIONS --------------------------
# ----------------- ENTITY CACHING | STATE MANAGEMENT
STATE_CACHE = {}
def get_cached_state(entity_id):
    """Load entity state from cache or fetch it if not available."""
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


# -------------------- AUTOMATIONS
# ---------------------------------------
def deactivate_automations(automation_ids, persistent_list_entity):
    """ 
    receives list of automations entity id's
        iterates over, and deactivates active automations. 
        persists list of deactivated automations in a input_select.
    """
    active_automations = []
    for automation_id in automation_ids:
        try:
            # Check if automation exists and is currently on
            state = get_cached_state(automation_id)
            if state is not None:
                if state.state == 'on':
                    active_automations.append(automation_id)
                # Disable automation
                hass.services.call('automation', 'turn_off', {'entity_id': automation_id})
            else:
                logger.warning("Warning: Automation entity not found. {}".format(automation_id))
        except Exception as ex:
            logger.error("Error disabling automation {} {}".format(automation_id, ex))
    if active_automations:
        try: # save list of automations that'd been disabled.
            hass.services.call('input_select', 'set_options', {
                'entity_id': persistent_list_entity,
                'options': active_automations
            })
            # Immediately select the first valid option ( prevents warnings and issues )
            hass.services.call('input_select', 'select_option', {
                'entity_id': persistent_list_entity,
                'option': active_automations[0]
            })
        except Exception as ex:
            logger.error("Error storing deactivated automations. {}".format(ex))


def activate_automations(persistent_list_entity):
    try:
        persistant_entity = get_cached_state(persistent_list_entity)
        persistant_list = persistant_entity.attributes.get('options', [])
        if persistant_list:
            for automation_id in persistant_list:
                if automation_id:
                    hass.services.call('automation', 'turn_on', {'entity_id': automation_id})
    except Exception as ex:
        logger.error("Error restoring automations. {}".format(ex))
    
    try:
        replace_options = ['placeholder']
        hass.services.call('input_select', 'set_options', {
            'entity_id': persistent_list_entity,
            'options': replace_options
        })
        # Immediately select the first valid option ( prevents warnings and issues )
        hass.services.call('input_select', 'select_option', {
            'entity_id': persistent_list_entity,
            'option': replace_options[0]
        })
    except Exception as ex:
        logger.error("Error clearing stored automations. {}".format(ex))


# -------------------- SCENES
# ---------------------------------------
def activate_scenes(scenes):
    """receives list of strings, scene_ids, iterates over and activates each scenes"""
    for entity_id in scenes:
        try:
            scene_state = get_cached_state(entity_id)
            if scene_state is not None:
                hass.services.call('scene', 'turn_on', {'entity_id': entity_id})
            else:
                logger.warning("Warning: Scene entity not found. {}".format(entity_id))
        except Exception as ex:
            logger.error("Error activating scene {} {}".format(entity_id, ex))


def deactivate_scenes(scenes):
    for entity_id in scenes:
        try:
            scene_state = get_cached_state(entity_id)
            if scene_state is not None:
                hass.services.call('scene', 'turn_off', {'entity_id': entity_id})
            else:
                logger.warning("Warning: Scene entity not found. {}".format(entity_id))
        except Exception as ex:
            logger.error("Error deactivating scene {} {}".format(entity_id, ex))


# -------------------- LIGHTS
# ---------------------------------------
def activate_lights(lights):
    """handles light list of objects, parses them out and activates them."""
    for light in lights:
        entity_id = light.get('entity_id')
        if not entity_id:
            continue
        try:
            light_state = get_cached_state(entity_id)
            if light_state is None:
                logger.warning("Warning: Light entity not found. {}".format(entity_id))
                continue
            
            light_params = {'entity_id': entity_id}
            if 'brightness' in light:
                light_params['brightness'] = light['brightness']
            elif 'brightness_pct' in light:
                light_params['brightness_pct'] = light['brightness_pct']
            
            if 'rgb_color' in light:
                light_params['rgb_color'] = light['rgb_color']
            elif 'color_temp_kelvin' in light:
                light_params['color_temp_kelvin'] = light['color_temp_kelvin']
            
            if 'transition' in light:
                light_params['transition'] = light['transition']

            hass.services.call('light', 'turn_on', light_params)
        except Exception as ex:
            logger.error("Error setting light {} {}".format(entity_id,ex))


def deactivate_lights(lights):
    for light in lights:
        entity_id = light.get('entity_id')
        if not entity_id:
            continue
        try:
            light_state = get_cached_state(entity_id)
            if light_state is not None:
                hass.services.call('light', 'turn_off', {'entity_id': entity_id})
            else:
                logger.warning("Warning: Light entity not found. {}".format(entity_id))            
        except Exception as ex:
            logger.error("Error turning off light {} {}".format(entity_id,ex))


# -------------------- DURATION | TIMER
# ---------------------------------------
def set_duration_timer(timer_entity, duration):
    try:
        hass.services.call('timer', 'start', {
            'entity_id': timer_entity,
            'duration': duration
        })
    except Exception as ex:
        logger.error("Error setting up timer {}".format(ex))


def cancel_duration_timer(timer_entity):
    try:
        timer_state = get_cached_state(timer_entity)
        if timer_state is not None and timer_state.state == 'active':
            hass.services.call('timer', 'cancel', {'entity_id': timer_entity})
    except Exception as ex:
        logger.error("Error canceling timer. {}".format(ex))


# -------------------------------------------------------
# Main Logic Execution
# -------------------------------------------------------
# Get parameters from data 
override_id = data.get('override_id', 'default')
automation_ids = data.get('automation_ids', [])
scenes = data.get('scenes') or [] # scenes must be a list of Strings, just like automation_ids
lights = data.get('lights') or [] # list of objects containing light entity_id, brightness_pct, color_temp_kelvin/color_rgb
duration = data.get('duration', None)
is_overriding = data.get('is_overriding', 1)
timer_entity = f"timer.override_{override_id}_timer"
persistent_list_entity = f"input_select.override_{override_id}_automations"

# prep cache
entities_to_cache = automation_ids + [timer_entity, persistent_list_entity]
if isinstance(automation_ids, str): # convert automation_ids to list if received as string.
    automation_ids = [id.strip() for id in automation_ids.split(',') if id.strip()]
if scenes:
    for scene_entity_id in scenes:
        entities_to_cache.append(scene_entity_id)
if lights:
    for light in lights:
        light_entity_id =  light.get("entity_id")
        if light_entity_id:
            entities_to_cache.append(light_entity_id)
        
# load cache
for entity_id in entities_to_cache:
    get_cached_state(entity_id)


is_overriding = bool(is_overriding)
if is_overriding:
    # --------------------------------------------------
    # OVERRIDE AUTOMATIONS
    # --------------------------------------------------
    logger.info(f"Activating override mode: {override_id}")
    deactivate_automations(automation_ids, persistent_list_entity)
    if scenes:
        activate_scenes(scenes)
    if lights:
        activate_lights(lights)
    if duration:
        set_duration_timer(timer_entity, duration)

else:
    # --------------------------------------------------
    # RESTORE AUTOMATIONS
    # --------------------------------------------------
    logger.info(f"Deactivating override mode: {override_id}")
    if scenes:
        deactivate_scenes(scenes)
    if lights:
        deactivate_lights(lights)
    cancel_duration_timer(timer_entity)
    activate_automations(persistent_list_entity)

STATE_CACHE.clear()