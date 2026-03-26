from datetime import timedelta
from time import timezone

import supabase
from supabase_auth import datetime

def attempt_login(student_id, entered_password):
    # Fetch the user
    response = supabase.table("users").select("*").eq("student_id", student_id).execute()
    
    if not response.data:
        return False, "Wrong / Failed Credentials."
        
    user = response.data[0]
    
    # 1. Check if currently locked out (Req 7)
    if user.get('locked_until'):
        lock_time = datetime.fromisoformat(user['locked_until'])
        if lock_time > datetime.now(timezone.utc):
            return False, "Multiple users are trying to use your credentials. Login paused for 2 minutes."
            
    # 2. Check if already logged in elsewhere (Req 6)
    if user.get('is_active'):
        return False, "Your session is already active on another PC."
        
    # 3. Check password
    if user['password'] != entered_password:
        return False, "Wrong / Failed Credentials."
        
    # 4. Success - mark user as active in the database
    supabase.table("users").update({"is_active": True}).eq("student_id", student_id).execute()
    return True, "Success"

def logout_user(student_id):
    # Run this when the user clicks logout, shuts down, or goes inactive for 20 mins (Req 4)
    supabase.table("users").update({"is_active": False}).eq("student_id", student_id).execute()

def trigger_lockout(student_id):
    # Run this if your app detects multiple simultaneous login clicks
    lock_time = datetime.now(timezone.utc) + timedelta(minutes=2)
    supabase.table("users").update({"locked_until": lock_time.isoformat()}).eq("student_id", student_id).execute()