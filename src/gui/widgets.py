import tkinter as tk
import io
from PIL import Image, ImageTk
from .constants import *

def sep(parent, color=BORDER, **kw):
    tk.Frame(parent, height=1, bg=color, **kw).pack(fill="x")

class MarqueeLabel(tk.Canvas):
    """A canvas-based label that scrolls text pixel-by-pixel for smooth animation."""
    def __init__(self, parent, text="", speed=25, **kw):
        # Intercept and map Label kwargs to Canvas equivalents
        kw.pop('display_width', None)
        kw.pop('anchor', None)
        self.bg_color = kw.pop('bg', BG)
        self.fg_color = kw.pop('fg', ACCENT_DIM)
        self.font = kw.pop('font', FONT_STATION2)

        super().__init__(parent, bg=self.bg_color, highlightthickness=0, height=20, **kw)

        self.full_text = text
        self.speed = speed
        self._after_id = None
        self.view_width = 0
        self.text_width = 0
        self.gap = 40  # Pixel gap between the end of the text and the looping start

        # We use two text objects to create the seamless looping illusion
        self.t1 = self.create_text(0, 10, text="", fill=self.fg_color, font=self.font, anchor="w")
        self.t2 = self.create_text(0, 10, text="", fill=self.fg_color, font=self.font, anchor="w", state="hidden")

        self.bind("<Configure>", self._on_resize)
        self.set_text(text)

    def config(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)

        if 'text' in kw:
            self.set_text(kw.pop('text'))
        if 'fg' in kw:
            self.fg_color = kw.pop('fg')
            self.itemconfig(self.t1, fill=self.fg_color)
            self.itemconfig(self.t2, fill=self.fg_color)
        if 'bg' in kw:
            self.bg_color = kw.pop('bg')
            super().config(bg=self.bg_color)

        kw.pop('display_width', None)
        kw.pop('anchor', None)

        if kw:
            super().config(**kw)

    # Alias configure to config to strictly match Tkinter's API
    configure = config

    def set_text(self, text):
        if self.full_text == text and self.text_width > 0: return
        self.full_text = text
        self.itemconfig(self.t1, text=self.full_text)

        bbox = self.bbox(self.t1)
        self.text_width = (bbox[2] - bbox[0]) if bbox else 0

        self._reset_animation()

    def _on_resize(self, event):
        self.view_width = event.width
        self._reset_animation()

    def _reset_animation(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

        cy = self.winfo_height() // 2 or 10
        self.coords(self.t1, 0, cy)

        if self.text_width > self.view_width and self.view_width > 0:
            self.itemconfig(self.t2, text=self.full_text, state="normal")
            self.coords(self.t2, self.text_width + self.gap, cy)
            self._animate()
        else:
            self.itemconfig(self.t2, state="hidden")

    def _animate(self):
        # Move both text nodes left by 1 pixel
        self.move(self.t1, -1, 0)
        self.move(self.t2, -1, 0)

        cy = self.winfo_height() // 2 or 10
        bbox1 = self.bbox(self.t1)
        bbox2 = self.bbox(self.t2)

        # If t1 scrolls completely out of view, snap it behind t2
        if bbox1 and bbox1[2] < 0:
            self.coords(self.t1, bbox2[2] + self.gap, cy)

        # If t2 scrolls completely out of view, snap it behind t1
        if bbox2 and bbox2[2] < 0:
            # Re-fetch bbox1 because t1 might have moved
            bbox1 = self.bbox(self.t1)
            self.coords(self.t2, bbox1[2] + self.gap, cy)

        self._after_id = self.after(self.speed, self._animate)

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

        # FIXED LAYOUT: Pack the Play button RIGHT first, before the text frame expands
        self.play_btn = tk.Label(
            self, text="▶", bg=PANEL, fg=TEXT_DIM,
            font=("Courier New", 14), padx=14, cursor="hand2"
        )
        self.play_btn.pack(side="right", fill="y")

        text_frame = tk.Frame(self, bg=PANEL)
        text_frame.pack(side="left", fill="both", expand=True)

        self.name_lbl = tk.Label(
            text_frame, text=name, bg=PANEL, fg=TEXT,
            font=FONT_STATION, anchor="w"
        )
        self.name_lbl.pack(fill="x", pady=(6, 1))

        # Using MarqueeLabel for long song names in the search results
        self.track_lbl = MarqueeLabel(
            text_frame, text="Loading live track...", bg=PANEL, fg=ACCENT_DIM,
            font=FONT_STATION2
        )
        self.track_lbl.pack(fill="x")

        self.id_lbl = tk.Label(
            text_frame, text=f"ID  {stn_id}", bg=PANEL, fg=TEXT_DIM,
            font=FONT_STATION2, anchor="w"
        )
        self.id_lbl.pack(fill="x", pady=(0, 6))

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
