class UIController:
    def __init__(self, stacked_widget):
        """
        Manages navigation between screens using a QStackedWidget.
        
        Index Mapping:
        0: Login Screen
        1: Session Screen
        2: Lock Screen
        """
        self.stack = stacked_widget

    def show_login(self):
        self.stack.setCurrentIndex(0)

    def show_session(self):
        self.stack.setCurrentIndex(1)

    def show_lock_screen(self):
        self.stack.setCurrentIndex(2)