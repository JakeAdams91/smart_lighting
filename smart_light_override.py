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
- automation_ids: List of automation entities to disable (automation.turn_on_livingroom)
- lights: List of light entities with desired settings (brightness, color_temp_kelvin, rgb_color)
- duration: Optional duration for auto-restore (format: "HH:MM:SS")
- scene_id: Optional scene to activate instead of individual light settings
- override_id: Identifier for this override instance (defaults to "default")
- is_activating: int 0 or 1 Bool indicates whether we're to override or restore
"""

# Initialize state cache
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

# Parse input parameters
override_id = data.get('override_id', 'default')
automation_ids = data.get('automation_ids', [])
lights = data.get('lights', [])
duration = data.get('duration', None)
scene_id = data.get('scene_id', None)
is_activating = data.get('is_activating', 1) # default activate override.

# Helper functions
def log_action(action, details=None):
    """Log override system actions with optional details."""
    message = f"Override System ({override_id}): {action}"
    if details:
        message += f" - {details}"
    logger.info(message)

# Setup override timer entity name
timer_entity = f"timer.override_{override_id}_timer"
input_text_entity = f"input_text.override_{override_id}_automations"

# Pre-load relevant entities into cache
entities_to_cache = automation_ids + [timer_entity, input_text_entity]
if scene_id:
    entities_to_cache.append(scene_id)
for light in lights:
    if 'entity_id' in light:
        entities_to_cache.append(light['entity_id'])

for entity_id in entities_to_cache:
    get_cached_state(entity_id)

# Check if we're activating or deactivating the override
is_activating = bool(is_activating)
log_action(action="is_activating", details=is_activating)
if is_activating:
    # --------------------------------------------------
    # ACTIVATION PHASE
    # --------------------------------------------------
    log_action("Activating override mode")
    
    # Store current state of automations in input_text for restoration
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
                log_action("Disabled automation", automation_id)
            else:
                log_action("Warning: Automation entity not found", automation_id)
        except Exception as e:
            log_action(f"Error disabling automation {automation_id}", str(e))
    
    # Store active automations in an input_text for later restoration
    try:
        hass.services.call('input_text', 'set_value', {
            'entity_id': input_text_entity,
            'value': ','.join(active_automations)
        })
    except Exception as e:
        log_action("Error storing automation state", str(e))
    
    # Apply lighting settings
    if scene_id:
        # Activate the specified scene
        try:
            scene_state = get_cached_state(scene_id)
            if scene_state is not None:
                hass.services.call('scene', 'turn_on', {'entity_id': scene_id})
                log_action("Activated scene", scene_id)
            else:
                log_action("Warning: Scene entity not found", scene_id)
        except Exception as e:
            log_action(f"Error activating scene {scene_id}", str(e))
    else:
        # Apply individual light settings
        for light in lights:
            entity_id = light.get('entity_id')
            if not entity_id:
                log_action("Warning: Light configuration missing entity_id")
                continue
                
            try:
                light_state = get_cached_state(entity_id)
                if light_state is None:
                    log_action("Warning: Light entity not found", entity_id)
                    continue
                    
                # Build service call parameters
                light_params = {'entity_id': entity_id}
                
                # Add optional parameters if they exist
                if 'brightness' in light:
                    # Convert percentage to 0-255 scale if needed
                    brightness = light['brightness']
                    if isinstance(brightness, int) and brightness <= 100:
                        brightness = int(brightness * 255 / 100)
                    light_params['brightness'] = brightness
                
                if 'color_temp_kelvin' in light:
                    light_params['color_temp_kelvin'] = light['color_temp_kelvin']
                
                if 'rgb_color' in light:
                    light_params['rgb_color'] = light['rgb_color']
                
                if 'transition' in light:
                    light_params['transition'] = light['transition']
                
                # Set the light state (default to turning on)
                state = light.get('state', 'on')
                if state.lower() == 'off':
                    hass.services.call('light', 'turn_off', {'entity_id': entity_id})
                    log_action("Turned off light", entity_id)
                else:
                    hass.services.call('light', 'turn_on', light_params)
                    log_action("Set light", f"{entity_id} with {light_params}")
            except Exception as e:
                log_action(f"Error setting light {entity_id}", str(e))
    
    # Set up timer for auto-restore if duration is provided
    if duration:
        try:
            hass.services.call('timer', 'start', {
                'entity_id': timer_entity,
                'duration': duration
            })
            log_action("Started override timer", f"Duration: {duration}")
            
            # Create an automation to handle the timer finishing
            # JUST CREATE AN AUTOMATION FOR EACH TIMER YOU WISH TO WATCH, 
            # OR CREATE A DYNAMIC AUTOMATION TO WATCH ALL YOUR TIMERS ASSOCIATED WITH THE OVERRIDE FUNCTIONS
            # timer_trigger_id = f"automation.override_{override_id}_timer"
            
            # hass.services.call('automation', 'turn_on', {
            #     'entity_id': timer_trigger_id
            # })
            # log_action("Enabled timer trigger automation", timer_trigger_id)
        except Exception as e:
            log_action("Error setting up timer", str(e))
    
    log_action("Override mode activated successfully")

else:
    # --------------------------------------------------
    # DEACTIVATION PHASE
    # --------------------------------------------------
    log_action("Deactivating override mode")
    
    # Cancel timer if it's running
    try:
        timer_state = get_cached_state(timer_entity)
        if timer_state is not None and timer_state.state == 'active':
            hass.services.call('timer', 'cancel', {'entity_id': timer_entity})
            log_action("Canceled override timer")
    except Exception as e:
        log_action("Error canceling timer", str(e))
    
    # Restore automations that were active before
    try:
        input_text_state = get_cached_state(input_text_entity)
        if input_text_state is not None:
            automation_text = input_text_state.state
            if automation_text and automation_text not in ["unknown", ""]:
                active_automations = automation_text.split(',')
                for automation_id in active_automations:
                    if automation_id:  # Skip empty strings
                        hass.services.call('automation', 'turn_on', {'entity_id': automation_id})
                        log_action("Restored automation", automation_id)
    except Exception as e:
        log_action("Error restoring automations", str(e))
    
    # Clear the stored automations
    try:
        hass.services.call('input_text', 'set_value', {
            'entity_id': input_text_entity,
            'value': ''
        })
    except Exception as e:
        log_action("Error clearing stored automation state", str(e))
    
    log_action("Override mode deactivated successfully")

# Clear cache at the end of execution
STATE_CACHE.clear()