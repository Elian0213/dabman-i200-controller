import tkinter as tk
from tkinter import font as tkfont
import requests
from requests.auth import HTTPBasicAuth
import logging
import sys

# --- Logging ---
logger = logging.getLogger("DABMAN_Controller")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ── Palette ────────────────────────────────────────────────────────────────────
BG          = "#0F1117"   # near-black base
PANEL       = "#171B24"   # raised surface
BORDER      = "#252A36"   # subtle border
GROOVE      = "#1C2130"   # inset groove
AMBER       = "#F5A623"   # primary accent / "live" indicator
AMBER_DIM   = "#7A5311"   # muted amber
RED_STOP    = "#C0392B"   # stop button
RED_DARK    = "#6E1F17"   # stop hover bg
GREEN_ON    = "#27AE60"   # connected state
STEEL       = "#8892A4"   # secondary text
TEXT        = "#D8DEE9"   # primary text
TEXT_DIM    = "#4C5568"   # disabled text
WHITE       = "#FFFFFF"
TERMINAL_BG = "#050608"   # deep black for logs
TERMINAL_FG = "#A8C7FA"   # soft tech blue for log text

FONT_MONO   = ("Courier New", 10)
FONT_LABEL  = ("Courier New", 8)
FONT_TITLE  = ("Courier New", 13, "bold")
FONT_STATUS = ("Courier New", 9, "bold")
FONT_BTN    = ("Courier New", 9, "bold")
FONT_LOG    = ("Courier New", 8)

class DABMANI400:
    def __init__(self, ip, log_callback):
        self.ip = ip
        self.auth = HTTPBasicAuth("su3g4go6sk7", "ji39454xu/^")
        self.log = log_callback

    def _req(self, path, port=80):
        try:
            url = f"http://{self.ip}:{port}{path}"
            self.log(f">>> REQ: GET {url}")
            r = requests.get(url, auth=self.auth, timeout=5)

            # Handle binary data like playlogo
            if 'image' in r.headers.get('Content-Type', ''):
                self.log(f"<<< RES: [{r.status_code}] [Binary Image Data]")
                return "[Image]"

            # Truncate extremely long XML logs for the UI to prevent freezing
            res_text = r.text.strip()
            display_text = res_text if len(res_text) < 500 else res_text[:500] + "\n...[TRUNCATED]"
            self.log(f"<<< RES: [{r.status_code}]\n{display_text}")
            return r.text
        except Exception as e:
            self.log(f"!!! ERR: {e}")
            return ""

def sep(parent, **kw):
    """1-px hairline separator."""
    tk.Frame(parent, height=1, bg=BORDER, **kw).pack(fill="x")

class PanelLabel(tk.Frame):
    """Section header with stamped-label look."""
    def __init__(self, parent, text, **kw):
        super().__init__(parent, bg=GROOVE, **kw)
        tk.Label(
            self, text=f"  {text}  ",
            bg=GROOVE, fg=AMBER_DIM,
            font=FONT_LABEL,
            padx=4, pady=3
        ).pack(side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(0, 6))

class IndustrialEntry(tk.Frame):
    """Entry styled as a recessed industrial readout."""
    def __init__(self, parent, width=20, **kw):
        super().__init__(parent, bg=BORDER, bd=0, **kw)
        inner = tk.Frame(self, bg=GROOVE, padx=1, pady=1)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.entry = tk.Entry(
            inner,
            bg=GROOVE, fg=AMBER,
            insertbackground=AMBER,
            relief="flat", bd=0,
            font=FONT_MONO,
            width=width,
        )
        self.entry.pack(fill="both", expand=True, padx=6, pady=5)

    def get(self): return self.entry.get()
    def insert(self, idx, val): self.entry.insert(idx, val)
    def delete(self, *a): self.entry.delete(*a)

class IndustrialButton(tk.Frame):
    """Tactile industrial button with hover + press states."""
    def __init__(self, parent, text, command=None, accent=AMBER,
                 accent_dark="#7A5311", width=9, **kw):
        super().__init__(parent, bg=BORDER, bd=0, **kw)
        self.command = command
        self.accent  = accent
        self.accent_dark = accent_dark

        self.btn = tk.Label(
            self,
            text=text,
            bg=PANEL, fg=accent,
            font=FONT_BTN,
            width=width,
            pady=5,
            cursor="hand2",
        )
        self.btn.pack(padx=1, pady=1, fill="both", expand=True)

        self.btn.bind("<Enter>",    self._hover)
        self.btn.bind("<Leave>",    self._leave)
        self.btn.bind("<Button-1>", self._press)
        self.btn.bind("<ButtonRelease-1>", self._release)

    def _hover(self, _):   self.btn.config(bg=GROOVE)
    def _leave(self, _):   self.btn.config(bg=PANEL)
    def _press(self, _):   self.btn.config(bg=self.accent_dark, fg=WHITE)
    def _release(self, e):
        self.btn.config(bg=GROOVE, fg=self.accent)
        if self.command: self.command()

class StatusIndicator(tk.Frame):
    """LED + text status readout."""
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self.dot = tk.Canvas(self, width=10, height=10, bg=PANEL,
                             highlightthickness=0)
        self.dot.pack(side="left", padx=(10, 6))
        self._oval = self.dot.create_oval(1, 1, 9, 9, fill=TEXT_DIM, outline="")

        self.label = tk.Label(self, text="NOT CONNECTED",
                              bg=PANEL, fg=STEEL,
                              font=FONT_STATUS)
        self.label.pack(side="left")

    def set(self, text, state="idle"):
        colors = {
            "idle":    (TEXT_DIM, STEEL),
            "ok":      (GREEN_ON, TEXT),
            "playing": (AMBER,    AMBER),
            "error":   (RED_STOP, TEXT),
        }
        dot_c, txt_c = colors.get(state, colors["idle"])
        self.dot.itemconfig(self._oval, fill=dot_c)
        self.label.config(text=text.upper(), fg=txt_c)

class App:
    def __init__(self, root):
        self.root  = root
        self.radio = None

        root.title("DABMAN i400 Master Control")
        root.geometry("1100x800")
        root.configure(bg=BG)

        self._build_title_bar()
        self._build_body()

    def ui_log(self, message):
        """Appends a message to the UI terminal."""
        self.terminal.config(state="normal")
        self.terminal.insert("end", message + "\n\n")
        self.terminal.see("end")
        self.terminal.config(state="disabled")
        self.root.update_idletasks()

    def get_radio(self):
        """Helper to ensure radio object exists with current IP."""
        if not self.radio or self.radio.ip != self.ip_entry.get():
            self.radio = DABMANI400(self.ip_entry.get(), self.ui_log)
        return self.radio

    # ── Layout builders ────────────────────────────────────────────────────────
    def _build_title_bar(self):
        bar = tk.Frame(self.root, bg=PANEL, pady=0)
        bar.pack(fill="x")
        tk.Frame(bar, width=4, bg=AMBER).pack(side="left", fill="y")
        tk.Label(bar, text="DABMAN  i400", bg=PANEL, fg=TEXT,
                 font=FONT_TITLE, padx=14, pady=11).pack(side="left")
        tk.Label(bar, text="API TEST CONSOLE", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 7, "bold"), padx=0, pady=0).pack(
                     side="left", anchor="s", pady=(0, 3))
        tk.Label(bar, text="●  LIVE", bg=PANEL, fg=AMBER_DIM,
                 font=("Courier New", 7, "bold"), padx=14).pack(side="right")
        sep(self.root)

    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Split into Left (Controls) and Right (Logs)
        left_col = tk.Frame(body, bg=BG, width=500)
        left_col.pack(side="left", fill="y", expand=False)
        left_col.pack_propagate(False) # lock width

        right_col = tk.Frame(body, bg=BG)
        right_col.pack(side="right", fill="both", expand=True, padx=(16, 0))

        # --- LEFT COLUMN: CONTROLS ---
        # 1. Connection & Status
        PanelLabel(left_col, "NETWORK / STATUS").pack(fill="x", pady=(0, 6))
        conn_row = tk.Frame(left_col, bg=BG)
        conn_row.pack(fill="x")
        self.ip_entry = IndustrialEntry(conn_row, width=15)
        self.ip_entry.insert(0, "192.168.215.61")
        self.ip_entry.pack(side="left", padx=(0, 8))
        IndustrialButton(conn_row, text="INIT/CONNECT", command=self.cmd_init, width=14).pack(side="left")

        status_wrap = tk.Frame(left_col, bg=PANEL)
        status_wrap.pack(fill="x", pady=(8, 0))
        self.status = StatusIndicator(status_wrap)
        self.status.pack(fill="x", pady=8)

        # 2. System Info / Lists (No Params)
        tk.Frame(left_col, bg=BG, height=12).pack()
        PanelLabel(left_col, "SYSTEM & LISTS (NO PARAMS)").pack(fill="x", pady=(0, 6))
        grid_sys = tk.Frame(left_col, bg=BG)
        grid_sys.pack(fill="x")

        btns = [
            ("Sys Info", lambda: self.get_radio()._req("/GetSystemInfo")),
            ("Play Info", lambda: self.get_radio()._req("/playinfo")),
            ("Play Status", lambda: self.get_radio()._req("/background_play_status")),
            ("FM Status", lambda: self.get_radio()._req("/GetFMStatus")),
            ("BT Status", lambda: self.get_radio()._req("/GetBTStatus")),
            ("IR Device XML", lambda: self.get_radio()._req("/irdevice.xml")),
            ("Web Fav List", lambda: self.get_radio()._req("/hotkeylist")),
            ("FM Fav List", lambda: self.get_radio()._req("/GetFMFAVlist")),
            ("DAB Fav List", lambda: self.get_radio()._req("/DABhotkeylist")),
            ("PlayLogo", lambda: self.get_radio()._req("/playlogo.jpg", port=8080)),
        ]
        for i, (txt, cmd) in enumerate(btns):
            row, col = divmod(i, 3)
            f = tk.Frame(grid_sys, bg=BG)
            f.grid(row=row, column=col, padx=2, pady=2, sticky="ew")
            grid_sys.columnconfigure(col, weight=1)
            IndustrialButton(f, text=txt, command=cmd, width=12).pack(fill="x")

        # 3. Action Commands (With Params)
        tk.Frame(left_col, bg=BG, height=12).pack()
        PanelLabel(left_col, "ACTIONS (WITH PARAMS)").pack(fill="x", pady=(0, 6))

        def make_param_row(label_txt, default_val, btn_txt, command):
            row = tk.Frame(left_col, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label_txt, bg=BG, fg=TEXT_DIM, font=FONT_LABEL, width=10, anchor="w").pack(side="left")
            ent = IndustrialEntry(row, width=15)
            ent.insert(0, default_val)
            ent.pack(side="left", padx=(0, 8))
            IndustrialButton(row, text=btn_txt, command=lambda e=ent: command(e.get()), width=12).pack(side="left")
            return ent

        self.key_ent = make_param_row("SendKey ID", "29", "SEND KEY", lambda val: self.get_radio()._req(f"/Sendkey?key={val}"))
        self.stn_ent = make_param_row("Station ID", "91_6", "PLAY STN", lambda val: self.get_radio()._req(f"/play_stn?id={val}"))
        self.fmf_ent = make_param_row("FM Fav ID", "1", "PLAY FM FAV", lambda val: self.get_radio()._req(f"/GotoFMfav?fav={val}"))
        self.dab_ent = make_param_row("DAB Fav ID", "1", "PLAY DAB FAV", lambda val: self.get_radio()._req(f"/playDABhotkey?key={val}"))
        self.srch_ent = make_param_row("Search Str", "radio", "SEARCH", lambda val: self.get_radio()._req(f"/searchstn?str={val}"))
        self.child_ent = make_param_row("GoChild ID", "100", "GO CHILD", lambda val: self.get_radio()._req(f"/gochild?id={val}"))
        self.url_ent = make_param_row("Local URL", "http://x/a.wav", "PLAY URL", lambda val: self.get_radio()._req(f"/LocalPlay?url={val}"))

        # Vol / Mute row (custom because 2 inputs)
        vol_row = tk.Frame(left_col, bg=BG)
        vol_row.pack(fill="x", pady=2)
        tk.Label(vol_row, text="Vol / Mute", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, width=10, anchor="w").pack(side="left")
        self.vol_ent = IndustrialEntry(vol_row, width=5)
        self.vol_ent.insert(0, "9")
        self.vol_ent.pack(side="left", padx=(0, 4))
        self.mute_ent = IndustrialEntry(vol_row, width=5)
        self.mute_ent.insert(0, "0")
        self.mute_ent.pack(side="left", padx=(0, 8))
        IndustrialButton(vol_row, text="SET VOL", command=lambda: self.get_radio()._req(f"/setvol?vol={self.vol_ent.get()}&mute={self.mute_ent.get()}"), width=12).pack(side="left")

        # 4. Playback Controls
        tk.Frame(left_col, bg=BG, height=12).pack()
        PanelLabel(left_col, "PLAYBACK CONTROL").pack(fill="x", pady=(0, 6))
        pb_row = tk.Frame(left_col, bg=BG)
        pb_row.pack(fill="x")
        IndustrialButton(pb_row, text="■ STOP", command=lambda: self.get_radio()._req("/stop"), accent=RED_STOP, accent_dark=RED_DARK, width=10).pack(side="left", padx=(0,4))
        IndustrialButton(pb_row, text="EXIT", command=lambda: self.get_radio()._req("/exit"), width=10).pack(side="left", padx=(0,4))
        IndustrialButton(pb_row, text="BACK", command=lambda: self.get_radio()._req("/back"), width=10).pack(side="left")


        # --- RIGHT COLUMN: LOG TERMINAL ---
        PanelLabel(right_col, "API RESPONSE TERMINAL").pack(fill="x", pady=(0, 6))

        term_frame = tk.Frame(right_col, bg=BORDER, bd=1)
        term_frame.pack(fill="both", expand=True)

        self.terminal = tk.Text(
            term_frame, bg=TERMINAL_BG, fg=TERMINAL_FG,
            font=FONT_LOG, wrap="word", state="disabled",
            insertbackground=AMBER, selectbackground=GROOVE, bd=0, padx=8, pady=8
        )
        self.terminal.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(term_frame, command=self.terminal.yview, bg=PANEL, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        self.terminal.config(yscrollcommand=scrollbar.set)

        # Clear logs button
        tk.Frame(right_col, bg=BG, height=6).pack()
        IndustrialButton(right_col, text="CLEAR TERMINAL", command=self.clear_logs, accent=STEEL, width=16).pack(anchor="e")

    # ── Actions ────────────────────────────────────────────────────────────────
    def clear_logs(self):
        self.terminal.config(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.config(state="disabled")

    def cmd_init(self):
        radio = self.get_radio()
        txt = radio._req("/init?language=en")
        if txt and "<cur_play_name>" in txt:
            try:
                name = txt.split("<cur_play_name>")[1].split("</cur_play_name>")[0]
                self.status.set(f"Playing  ›  {name}", "playing")
            except IndexError:
                self.status.set("Connected  ·  Idle", "ok")
        elif txt:
            self.status.set("Connected  ·  Idle", "ok")
        else:
            self.status.set("Connection failed", "error")

if __name__ == "__main__":
    root = tk.Tk()
    app  = App(root)
    root.mainloop()
