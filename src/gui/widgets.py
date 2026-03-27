import tkinter as tk
import io
from PIL import Image, ImageTk
from .constants import *

def sep(parent, color=BORDER, **kw):
    tk.Frame(parent, height=1, bg=color, **kw).pack(fill="x")

class PanelLabel(tk.Frame):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, bg=BG, **kw)
        tk.Label(
            self, text=text.upper(),
            bg=BG, fg=ACCENT_DIM, font=("Courier New", 7, "bold"), padx=0, pady=4
        ).pack(side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(8, 0))

class IndustrialEntry(tk.Frame):
    def __init__(self, parent, width=20, **kw):
        super().__init__(parent, bg=BORDER, bd=0, **kw)
        inner = tk.Frame(self, bg=GROOVE, padx=1, pady=1)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.entry = tk.Entry(
            inner, bg=GROOVE, fg=ACCENT, insertbackground=ACCENT,
            relief="flat", bd=0, font=FONT_MONO, width=width,
        )
        self.entry.pack(fill="both", expand=True, padx=6, pady=5)

    def get(self): return self.entry.get()
    def insert(self, idx, val): self.entry.insert(idx, val)
    def delete(self, *a): self.entry.delete(*a)

class IndustrialButton(tk.Frame):
    def __init__(self, parent, text, command=None, accent=ACCENT,
                 accent_dark=ACCENT_DIM, width=9, **kw):
        super().__init__(parent, bg=BORDER, bd=0, **kw)
        self.command = command
        self.accent = accent
        self.accent_dark = accent_dark
        self.btn = tk.Label(
            self, text=text, bg=PANEL2, fg=accent,
            font=FONT_BTN, width=width, pady=6, cursor="hand2"
        )
        self.btn.pack(padx=1, pady=1, fill="both", expand=True)
        self.btn.bind("<Enter>", self._hover)
        self.btn.bind("<Leave>", self._leave)
        self.btn.bind("<Button-1>", self._press)
        self.btn.bind("<ButtonRelease-1>", self._release)

    def _hover(self, _): self.btn.config(bg=GROOVE)
    def _leave(self, _): self.btn.config(bg=PANEL2)
    def _press(self, _): self.btn.config(bg=self.accent_dark, fg=WHITE)
    def _release(self, e):
        self.btn.config(bg=GROOVE, fg=self.accent)
        if self.command: self.command()

class StatusIndicator(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self.dot = tk.Canvas(self, width=8, height=8, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(12, 8))
        self._oval = self.dot.create_oval(0, 0, 8, 8, fill=TEXT_DIM, outline="")
        self.label = tk.Label(self, text="NOT CONNECTED", bg=PANEL, fg=STEEL, font=FONT_STATUS)
        self.label.pack(side="left")

    def set(self, text, state="idle"):
        colors = {
            "idle":    (TEXT_DIM, STEEL),
            "ok":      (GREEN_ON, TEXT),
            "playing": (ACCENT, ACCENT_GLOW),
            "error":   (RED_STOP, TEXT),
        }
        dot_c, txt_c = colors.get(state, colors["idle"])
        self.dot.itemconfig(self._oval, fill=dot_c)
        self.label.config(text=text.upper(), fg=txt_c)

class StationRow(tk.Frame):
    LOGO_SIZE = 40

    def __init__(self, parent, name, stn_id, index, on_play, on_select, **kw):
        super().__init__(parent, bg=PANEL, cursor="hand2", **kw)
        self.name = name
        self.stn_id = stn_id
        self.index = index
        self.on_play = on_play
        self.on_select = on_select
        self.selected = False
        self._photo = None

        self.accent_bar = tk.Frame(self, bg=PANEL, width=3)
        self.accent_bar.pack(side="left", fill="y")

        self.logo_cv = tk.Canvas(
            self, width=self.LOGO_SIZE, height=self.LOGO_SIZE,
            bg=GROOVE, highlightthickness=0
        )
        self.logo_cv.pack(side="left", padx=(6, 8), pady=6)
        self._placeholder()

        text_frame = tk.Frame(self, bg=PANEL)
        text_frame.pack(side="left", fill="both", expand=True)

        self.name_lbl = tk.Label(
            text_frame, text=name, bg=PANEL, fg=TEXT,
            font=FONT_STATION, anchor="w"
        )
        self.name_lbl.pack(fill="x", pady=(6, 1))

        self.track_lbl = tk.Label(
            text_frame, text="Loading live track...", bg=PANEL, fg=ACCENT_DIM,
            font=FONT_STATION2, anchor="w"
        )
        self.track_lbl.pack(fill="x")

        self.id_lbl = tk.Label(
            text_frame, text=f"ID  {stn_id}", bg=PANEL, fg=TEXT_DIM,
            font=FONT_STATION2, anchor="w"
        )
        self.id_lbl.pack(fill="x", pady=(0, 6))

        self.play_btn = tk.Label(
            self, text="▶", bg=PANEL, fg=TEXT_DIM,
            font=("Courier New", 14), padx=14, cursor="hand2"
        )
        self.play_btn.pack(side="right", fill="y")

        sep(self, color=BORDER)

        for widget in (self, text_frame, self.name_lbl, self.track_lbl, self.id_lbl):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Double-Button-1>", self._dbl)
            widget.bind("<Enter>", self._hover)
            widget.bind("<Leave>", self._leave)
        self.play_btn.bind("<Button-1>", lambda e: self.on_play(self.index))
        self.play_btn.bind("<Enter>", lambda e: self.play_btn.config(fg=ACCENT))
        self.play_btn.bind("<Leave>", lambda e: self.play_btn.config(fg=TEXT_DIM if not self.selected else ACCENT))

    def _placeholder(self):
        self.logo_cv.delete("all")
        self.logo_cv.create_rectangle(0, 0, self.LOGO_SIZE, self.LOGO_SIZE, fill=GROOVE, outline="")
        self.logo_cv.create_text(
            self.LOGO_SIZE // 2, self.LOGO_SIZE // 2,
            text="?", fill=TEXT_DIM, font=("Courier New", 14, "bold")
        )

    def set_logo(self, img_bytes):
        try:
            image = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            image.thumbnail((self.LOGO_SIZE, self.LOGO_SIZE), Image.Resampling.LANCZOS)
            bg_img = Image.new("RGBA", (self.LOGO_SIZE, self.LOGO_SIZE), GROOVE)
            ox = (self.LOGO_SIZE - image.width) // 2
            oy = (self.LOGO_SIZE - image.height) // 2
            bg_img.paste(image, (ox, oy), image)
            photo = ImageTk.PhotoImage(bg_img)
            self._photo = photo
            self.logo_cv.delete("all")
            self.logo_cv.create_image(0, 0, anchor="nw", image=photo)
        except Exception as e:
            print(f"Pillow failed to process the image: {e}")

    def set_track(self, track_name):
        self.track_lbl.config(text=track_name)

    def _click(self, e): self.on_select(self.index)
    def _dbl(self, e):   self.on_play(self.index)
    def _hover(self, e):
        if not self.selected:
            self._set_bg(GROOVE)
    def _leave(self, e):
        if not self.selected:
            self._set_bg(PANEL)

    def _set_bg(self, color):
        self.config(bg=color)
        for w in self.winfo_children():
            if isinstance(w, (tk.Label, tk.Frame)):
                try: w.config(bg=color)
                except Exception: pass
            for ww in w.winfo_children():
                try: ww.config(bg=color)
                except Exception: pass
        self.name_lbl.config(bg=color)
        self.track_lbl.config(bg=color)
        self.id_lbl.config(bg=color)
        self.play_btn.config(bg=color)

    def select(self, selected: bool):
        self.selected = selected
        if selected:
            self.accent_bar.config(bg=ACCENT)
            self._set_bg(GROOVE)
            self.name_lbl.config(fg=ACCENT_GLOW)
            self.track_lbl.config(fg=ACCENT)
            self.play_btn.config(fg=ACCENT)
        else:
            self.accent_bar.config(bg=PANEL)
            self._set_bg(PANEL)
            self.name_lbl.config(fg=TEXT)
            self.track_lbl.config(fg=ACCENT_DIM)
            self.play_btn.config(fg=TEXT_DIM)
