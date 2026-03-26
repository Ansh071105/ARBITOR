import customtkinter as ctk
from tkinter import messagebox
import sys
import os

# Import the DB handler you just created
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.db_handler import attempt_login

ctk.set_appearance_mode("dark")

class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Arbitor Login")
        
        # Security Requirement 3 & 8: Force fullscreen and stay on top
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", self.disable_event) # Block window closing

        # UI Layout
        self.label = ctk.CTkLabel(self, text="ARBITOR KIOSK", font=("Arial", 32, "bold"))
        self.label.pack(pady=(200, 50))

        self.username_entry = ctk.CTkEntry(self, placeholder_text="Student ID", width=300, height=40)
        self.username_entry.pack(pady=10)

        self.password_entry = ctk.CTkEntry(self, placeholder_text="Password", show="*", width=300, height=40)
        self.password_entry.pack(pady=10)

        self.login_btn = ctk.CTkButton(self, text="Login", command=self.handle_login, width=300, height=40)
        self.login_btn.pack(pady=20)

    def disable_event(self):
        # Prevents closing the app normally
        pass 

    def handle_login(self):
        student_id = self.username_entry.get()
        password = self.password_entry.get()
        
        # Check credentials and status against the cloud DB
        success, message = attempt_login(student_id, password)
        
        if success:
            self.destroy() # Close login window to start the session
            print("Session Started") 
            # We will link the session start logic here next
        else:
            # Requirements 5, 6, 7: Show specific popups
            messagebox.showerror("Login Alert", message)

if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()