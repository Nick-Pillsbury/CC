from inputs import get_gamepad
import subprocess
import os


class CarController(object):
    def __init__(self):
        self.LeftJoystickY = 0
        self.LeftJoystickX = 0
        self.LeftTrigger = 0
        self.RightTrigger = 0

# Target URL for your kiosk
url = "https://10.0.0.51:8889/stream/"

# Windows paths (Adjust for Mac/Linux if necessary)
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
C:\ProgramData\Microsoft\Windows\Start Menu\Programs

# Launch arguments for full lockdown
flags = [
    "--kiosk",                  # Enables kiosk mode
    "--start-fullscreen",       # Forces window to fill screen instantly
    "--noerrdialogs",           # Suppresses error popups
    "--disable-infobars"        # Removes "Chrome is being controlled" notices
]