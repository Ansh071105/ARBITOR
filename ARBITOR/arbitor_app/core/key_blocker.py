import keyboard

def block_system_keys():
    # Blocks Windows key, Alt+Tab, Task Manager shortcut, etc. (Requirement 3)
    blocked_keys = ['windows', 'alt+tab', 'ctrl+shift+esc', 'ctrl+esc', 'alt+space']
    
    for key in blocked_keys:
        try:
            keyboard.block_key(key)
        except ValueError:
            pass

def unblock_keys():
    keyboard.unhook_all()