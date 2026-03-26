import time
import threading
from pynput import mouse, keyboard
import sys
import os

# Import DB handler to update status on timeout
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.db_handler import logout_user

class SessionManager:
    def __init__(self, student_id, timeout_seconds=1200): # 1200 sec = 20 mins
        self.student_id = student_id
        self.timeout_seconds = timeout_seconds
        self.last_activity = time.time()
        self.is_active = True

    def reset_timer(self, *args):
        self.last_activity = time.time()

    def start_monitoring(self):
        # Start tracking mouse and keyboard
        self.mouse_listener = mouse.Listener(
            on_move=self.reset_timer, 
            on_click=self.reset_timer, 
            on_scroll=self.reset_timer
        )
        self.keyboard_listener = keyboard.Listener(on_press=self.reset_timer)
        
        self.mouse_listener.start()
        self.keyboard_listener.start()

        # Start the background countdown
        self.monitor_thread = threading.Thread(target=self._check_timeout, daemon=True)
        self.monitor_thread.start()

    def _check_timeout(self):
        while self.is_active:
            time.sleep(1)
            if time.time() - self.last_activity > self.timeout_seconds:
                self.end_session()

    def end_session(self):
        if not self.is_active: return
        self.is_active = False
        
        # Update cloud DB (Requirement 4)
        logout_user(self.student_id)
        
        print("Session Ended. Returning to login screen.")
        # In the final assembly, this will relaunch login_ui.py instead of closing
        os._exit(0)