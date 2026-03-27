import tkinter as tk
import ctypes
from gui.app import App

def enable_high_dpi():
    """Tells Windows to render the GUI crisply on HD/4K monitors."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

if __name__ == "__main__":
    enable_high_dpi()
    root = tk.Tk()
    app = App(root)
    root.mainloop()
