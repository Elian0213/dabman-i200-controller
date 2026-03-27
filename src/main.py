import tkinter as tk
import ctypes
import sys
import os
from gui.app import App

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def setup_windows_integration():
    """Tells Windows to render the GUI crisply and fixes taskbar icon grouping."""
    try:
        # Fix blurry text on HD/4K monitors
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

        # Tell Windows this is a unique app (forces it to use your icon in the taskbar)
        myappid = 'gibas.nl.dabmancontrol.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

if __name__ == "__main__":
    setup_windows_integration()

    root = tk.Tk()

    # Set the Window and Taskbar Icon
    try:
        root.iconbitmap(resource_path("icon.ico"))
    except Exception as e:
        print(f"Could not load icon: {e}")

    app = App(root)
    root.mainloop()
