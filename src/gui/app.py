# src/gui/app.py
import tkinter as tk
import urllib.parse
import threading
import io
import re
import requests
import concurrent.futures
from PIL import Image, ImageTk

from api.dabman import DABMANi200
from .constants import *
from .widgets import PanelLabel, IndustrialEntry, IndustrialButton, StatusIndicator, StationRow, MarqueeLabel, sep

class App:
    def __init__(self, root):
        self.root = root
        self.radio = None
        self.is_connected = False

        # Data caches
        self.public_stations_cache = []
        self.station_rows: list[StationRow] = []
        self.selected_index = -1

        # Fav Caches
        self.fav_cache = []
        self.fav_rows: list[StationRow] = []
        self.selected_fav_index = -1
        self.current_fav_mode = "WEB"

        # Now Playing State
        self.current_station_name = ""
        self.current_stream_url = None
        self.has_hi_res_logo = False

        self.api_lock = threading.Lock()
        self.current_vol = 5
        self.is_searching = False
        self.loading_frame = 0

        # Terminal State
        self.terminal_visible = False

        # Thread Pool for managing bulk network requests smoothly
        self.fetch_pool = concurrent.futures.ThreadPoolExecutor(max_workers=12)

        self.root.title("DABMAN i200  ·  CONTROL")
        self.root.geometry("1150x780")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self._build_title_bar()
        self._build_body()

        # Background workers
        self._poll_radio_logo()
        self._poll_current_track()
        self._poll_radio_state()

    # ── Logging ───────────────────────────────────────────────────────────────
    def ui_log(self, message):
        def _log():
            self.terminal.config(state="normal")
            self.terminal.insert("end", message + "\n\n")
            self.terminal.see("end")
            self.terminal.config(state="disabled")
        self.root.after(0, _log)

    def get_radio(self):
        if not self.radio or self.radio.ip != self.ip_entry.get():
            self.radio = DABMANi200(self.ip_entry.get(), self.ui_log)
        return self.radio

    def dispatch_req(self, path, port=80):
        def task():
            if not self.api_lock.acquire(blocking=False):
                self.ui_log(f"!!! ERR: Blocked concurrent request to {path}.")
                return
            try:
                self.get_radio().req(path, port)
            finally:
                self.api_lock.release()
        threading.Thread(target=task, daemon=True).start()

    # ── Combo API & Metadata Lookup ───────────────────────────────────────────
    def _lookup_station_combo(self, station_name):
        stream_url = None
        favicon_url = None
        logo_bytes = None

        try:
            rb_url = "https://all.api.radio-browser.info/json/stations/search"
            rb_params = {"name": station_name, "order": "votes", "reverse": "true", "hidebroken": "true", "limit": 3}
            resp = requests.get(rb_url, params=rb_params, timeout=3, headers={"User-Agent": "DABMANControl/1.0 gibas.nl"})

            if resp.status_code == 200:
                data = resp.json()
                if data:
                    best_station = next((s for s in data if s.get("favicon")), data[0])
                    stream_url = best_station.get("url_resolved") or best_station.get("url")
                    favicon_url = best_station.get("favicon")
        except Exception:
            pass

        if not favicon_url:
            try:
                tunein_url = f"http://opml.radiotime.com/Search.ashx?query={urllib.parse.quote(station_name)}&render=json"
                t_resp = requests.get(tunein_url, timeout=3)
                if t_resp.status_code == 200:
                    t_data = t_resp.json()
                    if t_data.get("body"):
                        for item in t_data["body"]:
                            if item.get("image"):
                                favicon_url = item["image"]
                                break
            except Exception:
                pass

        if favicon_url:
            if favicon_url.startswith("//"):
                favicon_url = "https:" + favicon_url
            try:
                img_resp = requests.get(favicon_url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
                if img_resp.status_code == 200 and img_resp.content:
                    logo_bytes = img_resp.content
            except Exception:
                pass

        return logo_bytes, stream_url

    def _get_icy_metadata(self, stream_url):
        try:
            headers = {'Icy-MetaData': '1', 'User-Agent': 'VLC/3.0.9 LibVLC/3.0.9'}
            with requests.get(stream_url, headers=headers, stream=True, timeout=(1.0, 1.5)) as r:
                metaint = int(r.headers.get('icy-metaint', 0))
                if metaint > 0:
                    r.raw.read(metaint)
                    meta_byte = r.raw.read(1)
                    if meta_byte:
                        meta_length = ord(meta_byte) * 16
                        if meta_length > 0:
                            meta_data = r.raw.read(meta_length).decode('utf-8', errors='ignore')
                            match = re.search(r"StreamTitle='([^']*)';", meta_data)
                            if match and match.group(1).strip():
                                return match.group(1).strip()
        except Exception:
            pass
        return None

    def _get_itunes_album_art(self, track_string):
        try:
            clean_track = re.sub(r'(\[.*?\]|\(.*?\)|ft\..*|feat\..*)', '', track_string, flags=re.IGNORECASE).strip()
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(clean_track)}&limit=1&entity=song"
            resp = requests.get(url, timeout=2)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("resultCount", 0) > 0:
                    art_url = data["results"][0].get("artworkUrl100")
                    if art_url:
                        art_url = art_url.replace("100x100bb", "600x600bb")
                        img_resp = requests.get(art_url, timeout=2)
                        if img_resp.status_code == 200:
                            return img_resp.content
        except Exception:
            pass
        return None

    # ── Now Playing Enrichment ────────────────────────────────────────────────
    def _trigger_now_playing_enrichment(self, station_name):
        self.current_station_name = station_name
        self.has_hi_res_logo = False
        self.current_stream_url = None

        self.now_playing_stn_lbl.config(text=station_name)
        self.now_playing_trk_lbl.config(text="Locating stream info...")

        def task():
            logo_bytes, stream_url = self._lookup_station_combo(station_name)

            if logo_bytes:
                self.has_hi_res_logo = True
                try:
                    image = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
                    image.thumbnail((130, 130), Image.Resampling.LANCZOS)
                    bg_img = Image.new("RGBA", (130, 130), GROOVE)
                    ox = (130 - image.width) // 2
                    oy = (130 - image.height) // 2
                    bg_img.paste(image, (ox, oy), image)

                    photo = ImageTk.PhotoImage(bg_img)
                    self.root.after(0, self._update_main_logo_ui, photo)
                except Exception:
                    pass

            if stream_url:
                self.current_stream_url = stream_url
                track = self._get_icy_metadata(stream_url)
                if track:
                    self.root.after(0, lambda t=f"♫ {track}": self.now_playing_trk_lbl.config(text=t))
                else:
                    self.root.after(0, lambda: self.now_playing_trk_lbl.config(text="Live Broadcast"))
            else:
                self.root.after(0, lambda: self.now_playing_trk_lbl.config(text="No stream data available"))

        self.fetch_pool.submit(task)

    def _poll_current_track(self):
        def task():
            if self.current_stream_url:
                track = self._get_icy_metadata(self.current_stream_url)
                if track:
                    self.root.after(0, lambda t=f"♫ {track}": self.now_playing_trk_lbl.config(text=t))

                    art_bytes = self._get_itunes_album_art(track)
                    if art_bytes:
                        try:
                            image = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
                            image.thumbnail((130, 130), Image.Resampling.LANCZOS)
                            photo = ImageTk.PhotoImage(image)
                            self.root.after(0, self._update_main_logo_ui, photo)
                        except Exception:
                            pass

        self.fetch_pool.submit(task)
        self.root.after(10000, self._poll_current_track)

    def _poll_radio_state(self):
        if self.is_connected:
            def task():
                if not self.api_lock.acquire(blocking=False):
                    return
                try:
                    res = self.radio.req("/init?language=en", silent=True)
                    if res and "<cur_play_name>" in res:
                        name = res.split("<cur_play_name>")[1].split("</cur_play_name>")[0]
                        if name != self.current_station_name:
                            self.root.after(0, self._trigger_now_playing_enrichment, name)
                finally:
                    self.api_lock.release()
            threading.Thread(target=task, daemon=True).start()

        self.root.after(5000, self._poll_radio_state)

    def _poll_radio_logo(self):
        if self.is_connected and self.radio and not self.has_hi_res_logo:
            threading.Thread(target=self._fetch_radio_logo_thread, daemon=True).start()
        self.root.after(2000, self._poll_radio_logo)

    def _fetch_radio_logo_thread(self):
        try:
            img_data = self.radio.req("/playlogo.jpg", port=8080, timeout=2.0, silent=True)
            if isinstance(img_data, bytes):
                image = Image.open(io.BytesIO(img_data))
                image.thumbnail((130, 130), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.root.after(0, self._update_main_logo_ui, photo)
        except Exception:
            pass

    def _update_main_logo_ui(self, photo):
        self.logo_label.config(image=photo, text="")
        self.logo_label.image = photo

    def _fetch_station_info_for_row(self, row: StationRow, station_name: str):
        def task():
            if not row.winfo_exists(): return
            logo_bytes, stream_url = self._lookup_station_combo(station_name)

            if not row.winfo_exists(): return
            if logo_bytes:
                self.root.after(0, row.set_logo, logo_bytes)

            if stream_url:
                track_name = self._get_icy_metadata(stream_url)
                if not row.winfo_exists(): return

                if track_name:
                    self.root.after(0, row.set_track, f"♫ {track_name}")
                else:
                    self.root.after(0, row.set_track, "Radio Stream Live")
            else:
                self.root.after(0, row.set_track, "Stream info unavailable")

        self.fetch_pool.submit(task)

    # ── Layout Builders ───────────────────────────────────────────────────────
    def _build_title_bar(self):
        bar = tk.Frame(self.root, bg=PANEL, pady=0)
        bar.pack(fill="x")
        tk.Frame(bar, width=3, bg=ACCENT).pack(side="left", fill="y")
        title_block = tk.Frame(bar, bg=PANEL)
        title_block.pack(side="left", padx=(16, 0), pady=8)
        tk.Label(title_block, text="DABMAN", bg=PANEL, fg=TEXT, font=FONT_TITLE).pack(side="left")
        tk.Label(title_block, text=" i200", bg=PANEL, fg=ACCENT, font=FONT_TITLE).pack(side="left")
        tk.Label(bar, text="MASTER CONTROL UNIT", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 7, "bold"), padx=12).pack(side="left", anchor="s", pady=(0, 4))

        # Right aligned buttons on title bar
        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=14, pady=4)

        # Toggle Terminal Button
        self.btn_toggle_term = tk.Label(right, text="[±] API LOGS", bg=PANEL, fg=TEXT_DIM, font=("Courier New", 9, "bold"), cursor="hand2")
        self.btn_toggle_term.pack(side="left", padx=(0, 20))
        self.btn_toggle_term.bind("<Button-1>", lambda e: self.cmd_toggle_terminal())
        self.btn_toggle_term.bind("<Enter>", lambda e: self.btn_toggle_term.config(fg=ACCENT))
        self.btn_toggle_term.bind("<Leave>", lambda e: self.btn_toggle_term.config(fg=ACCENT_GLOW if self.terminal_visible else TEXT_DIM))

        tk.Label(right, text="gibas.nl", bg=PANEL, fg=TEXT_DIM, font=("Courier New", 7)).pack(side="left")
        sep(self.root)

    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        self.left_col = tk.Frame(body, bg=BG, width=280)
        self.left_col.pack(side="left", fill="y", expand=False)
        self.left_col.pack_propagate(False)

        # Right col takes a fixed width when shown, but starts hidden
        self.right_col = tk.Frame(body, bg=BG, width=380)
        self.right_col.pack_propagate(False)

        # Mid col expands to take ALL remaining space
        self.mid_col = tk.Frame(body, bg=BG)
        self.mid_col.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self._build_left(self.left_col)
        self._build_right(self.right_col)
        self._build_mid(self.mid_col)

    def _build_left(self, col):
        PanelLabel(col, "Network").pack(fill="x", pady=(0, 6))
        conn_row = tk.Frame(col, bg=BG)
        conn_row.pack(fill="x")
        self.ip_entry = IndustrialEntry(conn_row, width=13)
        self.ip_entry.insert(0, "192.168.215.61")
        self.ip_entry.pack(side="left", padx=(0, 6))
        IndustrialButton(conn_row, text="CONNECT", command=self.cmd_init, width=9).pack(side="left")

        status_wrap = tk.Frame(col, bg=PANEL)
        status_wrap.pack(fill="x", pady=(8, 0))
        self.status = StatusIndicator(status_wrap)
        self.status.pack(fill="x", pady=8)
        sep(col)

        tk.Frame(col, bg=BG, height=14).pack()
        PanelLabel(col, "Now Playing").pack(fill="x", pady=(0, 6))

        logo_wrap = tk.Frame(col, bg=BORDER, width=140, height=140)
        logo_wrap.pack()
        logo_wrap.pack_propagate(False)
        self.logo_label = tk.Label(
            logo_wrap, bg=GROOVE,
            text="NO LOGO", fg=TEXT_DIM, font=FONT_LABEL, justify="center"
        )
        self.logo_label.pack(fill="both", expand=True, padx=1, pady=1)

        self.now_playing_stn_lbl = tk.Label(col, text="---", bg=BG, fg=TEXT, font=FONT_STATION)
        self.now_playing_stn_lbl.pack(fill="x", pady=(8, 2))

        self.now_playing_trk_lbl = MarqueeLabel(
            col, text="Ready", bg=BG, fg=ACCENT_GLOW,
            font=FONT_STATION2
        )
        self.now_playing_trk_lbl.pack(fill="x", pady=(0, 16))

        ctrl_outer = tk.Frame(col, bg=PANEL)
        ctrl_outer.pack(fill="x", pady=2)

        ctrl_row = tk.Frame(ctrl_outer, bg=PANEL)
        ctrl_row.pack(fill="none", expand=True, padx=10, pady=8)

        IndustrialButton(ctrl_row, text="■ STOP",
                         command=lambda: self.dispatch_req("/stop"),
                         accent=RED_STOP, accent_dark=RED_DARK, width=8).pack(side="left", padx=(0, 16))

        tk.Label(ctrl_row, text="VOL", bg=PANEL, fg=TEXT_DIM,
                 font=FONT_LABEL, anchor="e").pack(side="left", padx=(0, 4))
        IndustrialButton(ctrl_row, text="−", command=self.cmd_vol_down, width=2).pack(side="left", padx=2)
        self.vol_label = tk.Label(ctrl_row, text=str(self.current_vol),
                                  bg=GROOVE, fg=ACCENT, font=FONT_MONO, width=3)
        self.vol_label.pack(side="left", padx=4)
        IndustrialButton(ctrl_row, text="+", command=self.cmd_vol_up, width=2).pack(side="left", padx=2)

    def _build_mid(self, col):
        tab_bar = tk.Frame(col, bg=BG)
        tab_bar.pack(fill="x", pady=(0, 10))

        self.btn_tab_search = IndustrialButton(tab_bar, text="BROWSE", command=lambda: self._switch_tab("search"))
        self.btn_tab_search.pack(side="left", fill="x", expand=True, padx=(0, 2))

        self.btn_tab_fav = IndustrialButton(tab_bar, text="FAVORITES", command=lambda: self._switch_tab("fav"))
        self.btn_tab_fav.pack(side="left", fill="x", expand=True, padx=2)

        self.btn_tab_sys = IndustrialButton(tab_bar, text="INFO", command=lambda: self._switch_tab("sys"))
        self.btn_tab_sys.pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.tab_container = tk.Frame(col, bg=BG)
        self.tab_container.pack(fill="both", expand=True)

        self.tab_search = tk.Frame(self.tab_container, bg=BG)
        self.tab_fav = tk.Frame(self.tab_container, bg=BG)
        self.tab_sys = tk.Frame(self.tab_container, bg=BG)

        self._build_search_tab(self.tab_search)
        self._build_fav_tab(self.tab_fav)
        self._build_sys_tab(self.tab_sys)

        self._switch_tab("search")

    def _switch_tab(self, tab_name):
        for t in (self.tab_search, self.tab_fav, self.tab_sys):
            t.pack_forget()

        for b in (self.btn_tab_search, self.btn_tab_fav, self.btn_tab_sys):
            b.btn.config(fg=TEXT_DIM)

        if tab_name == "search":
            self.tab_search.pack(fill="both", expand=True)
            self.btn_tab_search.btn.config(fg=ACCENT_GLOW)
        elif tab_name == "fav":
            self.tab_fav.pack(fill="both", expand=True)
            self.btn_tab_fav.btn.config(fg=ACCENT_GLOW)
        elif tab_name == "sys":
            self.tab_sys.pack(fill="both", expand=True)
            self.btn_tab_sys.btn.config(fg=ACCENT_GLOW)

    def _build_search_tab(self, parent):
        PanelLabel(parent, "Radio-Browser Database").pack(fill="x", pady=(0, 8))

        search_row = tk.Frame(parent, bg=BG)
        search_row.pack(fill="x", pady=(0, 8))
        self.pub_search_ent = IndustrialEntry(search_row, width=20)
        self.pub_search_ent.insert(0, "NPO")
        self.pub_search_ent.pack(side="left", padx=(0, 6), fill="y")
        self.pub_search_ent.entry.bind("<Return>", lambda e: self.cmd_search())
        IndustrialButton(search_row, text="SEARCH", command=self.cmd_search, width=9).pack(side="left")

        list_outer = tk.Frame(parent, bg=BORDER, bd=1)
        list_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_outer, bg=PANEL, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview, bg=PANEL2, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        canvas.config(yscrollcommand=scrollbar.set)

        self.station_frame = tk.Frame(canvas, bg=PANEL)
        self.station_frame_id = canvas.create_window((0, 0), window=self.station_frame, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self.station_frame_id, width=canvas.winfo_width())

        self.station_frame.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self.station_frame_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units") if str(canvas) in str(self.root.winfo_containing(e.x_root, e.y_root)) else None)

        self.station_canvas = canvas

        self.search_status = tk.Label(parent, text="No search yet", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, anchor="w")
        self.search_status.pack(fill="x", pady=(4, 0))

    def _build_fav_tab(self, parent):
        PanelLabel(parent, "Device Presets").pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=(0, 8))

        IndustrialButton(btn_row, text="WEB", command=lambda: self.cmd_fetch_favs("WEB")).pack(side="left", fill="x", expand=True, padx=(0, 2))
        IndustrialButton(btn_row, text="DAB", command=lambda: self.cmd_fetch_favs("DAB")).pack(side="left", fill="x", expand=True, padx=2)
        IndustrialButton(btn_row, text="FM", command=lambda: self.cmd_fetch_favs("FM")).pack(side="left", fill="x", expand=True, padx=(2, 0))

        list_outer = tk.Frame(parent, bg=BORDER, bd=1)
        list_outer.pack(fill="both", expand=True)

        self.fav_canvas = tk.Canvas(list_outer, bg=PANEL, highlightthickness=0)
        self.fav_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=self.fav_canvas.yview, bg=PANEL2, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        self.fav_canvas.config(yscrollcommand=scrollbar.set)

        self.fav_station_frame = tk.Frame(self.fav_canvas, bg=PANEL)
        self.fav_frame_id = self.fav_canvas.create_window((0, 0), window=self.fav_station_frame, anchor="nw")

        def on_fav_configure(e):
            self.fav_canvas.configure(scrollregion=self.fav_canvas.bbox("all"))
            self.fav_canvas.itemconfig(self.fav_frame_id, width=self.fav_canvas.winfo_width())

        self.fav_station_frame.bind("<Configure>", on_fav_configure)
        self.fav_canvas.bind("<Configure>", lambda e: self.fav_canvas.itemconfig(self.fav_frame_id, width=e.width))

        self.fav_status = tk.Label(parent, text="Select a source to load favorites.", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, anchor="w")
        self.fav_status.pack(fill="x", pady=(4, 0))

    def _build_sys_tab(self, parent):
        PanelLabel(parent, "Hardware Diagnostics").pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=(0, 8))
        IndustrialButton(btn_row, text="REFRESH SYSTEM INFO", command=self.cmd_fetch_sys_info).pack(fill="x", expand=True)

        term_frame = tk.Frame(parent, bg=BORDER, bd=1)
        term_frame.pack(fill="both", expand=True)

        self.sys_text = tk.Text(
            term_frame, bg=TERMINAL_BG, fg=STEEL,
            font=("Courier New", 10), wrap="word", state="disabled",
            insertbackground=ACCENT, bd=0, padx=14, pady=14, spacing1=4
        )
        self.sys_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(term_frame, command=self.sys_text.yview, bg=PANEL, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        self.sys_text.config(yscrollcommand=scrollbar.set)

    def _build_right(self, col):
        PanelLabel(col, "API Terminal").pack(fill="x", pady=(0, 6))

        term_frame = tk.Frame(col, bg=BORDER, bd=1)
        term_frame.pack(fill="both", expand=True)

        self.terminal = tk.Text(
            term_frame, bg=TERMINAL_BG, fg=TERMINAL_FG,
            font=FONT_LOG, wrap="word", state="disabled",
            insertbackground=ACCENT, selectbackground=GROOVE,
            bd=0, padx=10, pady=10, spacing1=1
        )
        self.terminal.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(term_frame, command=self.terminal.yview, bg=PANEL, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        self.terminal.config(yscrollcommand=scrollbar.set)

        tk.Frame(col, bg=BG, height=6).pack()
        IndustrialButton(col, text="CLEAR", command=self.clear_logs, accent=STEEL, width=10).pack(anchor="e")

    # ── Fav Actions ───────────────────────────────────────────────────────────
    def cmd_fetch_favs(self, mode):
        self.fav_status.config(text=f"Loading {mode} favorites...", fg=ACCENT)
        for row in self.fav_rows:
            row.destroy()
        self.fav_rows.clear()

        def task():
            if not self.api_lock.acquire(blocking=False): return
            try:
                radio = self.get_radio()
                if mode == "WEB":
                    res = radio.req("/hotkeylist", timeout=10)
                elif mode == "DAB":
                    res = radio.req("/DABhotkeylist", timeout=10)
                else:
                    res = radio.req("/GetFMFAVlist", timeout=10)

                items = re.findall(r'<item[^>]*>(.*?)</item[^>]*>', res, re.IGNORECASE | re.DOTALL)

                results = []
                for item_str in items:
                    id_match = re.search(r'<id>(.*?)</id>', item_str, re.IGNORECASE)
                    name_match = re.search(r'<name>(.*?)</name>', item_str, re.IGNORECASE)
                    freq_match = re.search(r'<Freq>(.*?)</Freq>', item_str, re.IGNORECASE)

                    stn_id = id_match.group(1) if id_match else ""

                    if name_match:
                        name = name_match.group(1).replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')
                    elif freq_match:
                        name = f"{freq_match.group(1)} MHz"
                    else:
                        name = f"Preset {stn_id}"

                    if stn_id and name:
                        results.append((name, stn_id))

                self.root.after(0, self._render_fav_results, results, mode)
            except Exception as e:
                self.ui_log(f"!!! ERR FAV: {e}")
                self.root.after(0, self.fav_status.config, {"text": "Failed to load favorites", "fg": RED_STOP})
            finally:
                self.api_lock.release()

        threading.Thread(target=task, daemon=True).start()

    def _render_fav_results(self, results, mode):
        self.fav_status.config(text=f"Found {len(results)} {mode} favorites", fg=GREEN_ON)
        self.fav_cache = results
        self.current_fav_mode = mode

        for i, (name, stn_id) in enumerate(results):
            row = StationRow(
                self.fav_station_frame, name, stn_id, i,
                on_play=self.cmd_play_fav_index,
                on_select=self.cmd_select_fav_index,
            )
            row.pack(fill="x")
            self.fav_rows.append(row)

            if mode == "WEB":
                self._fetch_station_info_for_row(row, name)
            else:
                row.set_track(f"{mode} Radio Preset")

        self.fav_station_frame.update_idletasks()
        self.fav_canvas.configure(scrollregion=self.fav_canvas.bbox("all"))
        self.fav_canvas.yview_moveto(0)

    def cmd_select_fav_index(self, index):
        if self.selected_fav_index == index: return
        if 0 <= self.selected_fav_index < len(self.fav_rows):
            self.fav_rows[self.selected_fav_index].select(False)
        self.selected_fav_index = index
        if 0 <= index < len(self.fav_rows):
            self.fav_rows[index].select(True)

    def cmd_play_fav_index(self, index):
        if index < 0 or index >= len(self.fav_cache): return
        name, stn_id = self.fav_cache[index]
        mode = self.current_fav_mode

        self.cmd_select_fav_index(index)
        self.root.after(0, lambda: self.logo_label.config(image="", text="LOADING\nLOGO..."))

        if mode == "WEB":
            self.dispatch_req(f"/play_stn?id={stn_id}")
            self._trigger_now_playing_enrichment(name)
        elif mode == "DAB":
            self.dispatch_req(f"/playDABhotkey?key={index + 1}")
            self.root.after(0, lambda: self.now_playing_stn_lbl.config(text=name))
            self.root.after(0, lambda: self.now_playing_trk_lbl.config(text="DAB Digital Broadcast"))
        elif mode == "FM":
            self.dispatch_req(f"/GotoFMfav?fav={stn_id}")
            self.root.after(0, lambda: self.now_playing_stn_lbl.config(text=name))
            self.root.after(0, lambda: self.now_playing_trk_lbl.config(text="FM Analog Broadcast"))

    # ── Sys Info Actions ──────────────────────────────────────────────────────
    def cmd_fetch_sys_info(self):
        self.sys_text.config(state="normal")
        self.sys_text.delete("1.0", "end")
        self.sys_text.insert("end", "Fetching system info...\n")
        self.sys_text.config(state="disabled")

        def task():
            if not self.api_lock.acquire(blocking=False): return
            try:
                radio = self.get_radio()
                res = radio.req("/GetSystemInfo", timeout=10)

                pairs = re.findall(r'<([a-zA-Z0-9_]+)[^>]*>([^<]*)</\s*[a-zA-Z0-9_]+\s*>', res)
                data = {k: v.strip() for k, v in pairs}

                mac = data.get("MAC", "Unknown")
                if len(mac) == 12:
                    mac = ":".join(mac[i:i+2] for i in range(0, 12, 2))

                sw_ver = data.get("SW_Ver", "Unknown")
                status = data.get("status", "Unknown").capitalize()
                ssid   = data.get("SSID", "") or "N/A"
                signal = data.get("Signal", "0")
                enc    = data.get("Encryption", "--") or "None"
                if enc == "--": enc = "None"

                ip     = data.get("IP", "") or "N/A"
                subnet = data.get("Subnet", "") or "N/A"
                gw     = data.get("Gateway", "") or "N/A"
                dns1   = data.get("DNS1", "") or "N/A"
                dns2   = data.get("DNS2", "") or "N/A"

                out =  "📻 DEVICE INFORMATION\n"
                out += "──────────────────────────────────────────────────\n"
                out += f" Firmware Version  : {sw_ver}\n"
                out += f" MAC Address       : {mac}\n\n"

                out += "🌐 NETWORK STATUS\n"
                out += "──────────────────────────────────────────────────\n"
                out += f" Connection State  : {status}\n"
                out += f" Wi-Fi Network     : {ssid}\n"
                out += f" Signal Strength   : {signal}%\n"
                out += f" Security          : {enc}\n\n"

                out += "⚙️ IP CONFIGURATION\n"
                out += "──────────────────────────────────────────────────\n"
                out += f" IP Address        : {ip}\n"
                out += f" Subnet Mask       : {subnet}\n"
                out += f" Default Gateway   : {gw}\n"
                out += f" Primary DNS       : {dns1}\n"
                out += f" Secondary DNS     : {dns2}\n"

                self.root.after(0, self._render_sys_info, out)
            except Exception as e:
                self.root.after(0, self._render_sys_info, f"Failed to fetch info: {e}")
            finally:
                self.api_lock.release()

        threading.Thread(target=task, daemon=True).start()

    def _render_sys_info(self, text):
        self.sys_text.config(state="normal")
        self.sys_text.delete("1.0", "end")
        self.sys_text.insert("end", text)
        self.sys_text.config(state="disabled")

    # ── Core Actions ──────────────────────────────────────────────────────────
    def cmd_toggle_terminal(self):
        self.terminal_visible = not self.terminal_visible
        if self.terminal_visible:
            self.mid_col.pack_forget()
            self.right_col.pack(side="right", fill="y", padx=(14, 0))
            self.mid_col.pack(side="left", fill="both", expand=True, padx=(14, 0))
            self.btn_toggle_term.config(fg=ACCENT_GLOW)
        else:
            self.right_col.pack_forget()
            self.btn_toggle_term.config(fg=TEXT_DIM)

    def cmd_vol_up(self):
        if self.current_vol < 7:
            self.current_vol += 1
            self.vol_label.config(text=str(self.current_vol))
            self.dispatch_req(f"/setvol?vol={self.current_vol}&mute=0")

    def cmd_vol_down(self):
        if self.current_vol > 0:
            self.current_vol -= 1
            self.vol_label.config(text=str(self.current_vol))
            self.dispatch_req(f"/setvol?vol={self.current_vol}&mute=0")

    def _animate_loading(self):
        if not self.is_searching: return
        frames = ["◐", "◓", "◑", "◒"]
        frame = frames[self.loading_frame % len(frames)]
        self.loading_frame += 1
        self.search_status.config(text=f"  {frame}  Searching...", fg=ACCENT)
        self.root.after(120, self._animate_loading)

    def cmd_search(self):
        if not self.api_lock.acquire(blocking=False):
            self.ui_log("!!! ERR: Radio is busy.")
            return

        query = self.pub_search_ent.get().strip()
        if not query:
            self.api_lock.release()
            return

        for row in self.station_rows:
            row.destroy()

        self.station_rows.clear()
        self.station_canvas.yview_moveto(0)
        self.selected_index = -1

        self.is_searching = True
        self.loading_frame = 0
        self._animate_loading()

        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            self.ui_log(f">>> NATIVE DB: Searching for '{query}'...")
            radio = self.get_radio()

            res1 = radio.req(f"/searchstn?str={urllib.parse.quote(query)}", timeout=15)
            if not res1 or "<id>" not in res1:
                self.root.after(0, self._show_search_error, "No results or timeout.")
                return

            dir_id = re.search(r'<id>(.*?)</id>', res1, re.IGNORECASE).group(1)
            radio.req(f"/gochild?id={dir_id}", timeout=15)
            res3 = radio.req(f"/list?id={dir_id}&start=1&count=50", timeout=20)

            if not res3:
                self.root.after(0, self._show_search_error, "List fetch timed out.")
                return

            items = re.findall(r'<item>(.*?)</item>', res3, re.IGNORECASE | re.DOTALL)

            if not items:
                self.root.after(0, self._show_search_error, "No stations found.")
                return

            results = []
            for item_str in items:
                id_match   = re.search(r'<id>(.*?)</id>',     item_str, re.IGNORECASE)
                name_match = re.search(r'<name>(.*?)</name>', item_str, re.IGNORECASE)
                if id_match and name_match:
                    stn_id = id_match.group(1)
                    name   = name_match.group(1).replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')
                    results.append((name, stn_id))

            self.ui_log(f"<<< NATIVE DB: Found {len(results)} stations.")
            self.root.after(0, self._render_search_results, results)

        except Exception as e:
            self.ui_log(f"!!! ERR NATIVE DB: {e}")
            self.root.after(0, self._show_search_error, "Fatal search error.")
        finally:
            self.is_searching = False
            self.api_lock.release()

    def _show_search_error(self, message):
        self.is_searching = False
        self.search_status.config(text=f"  ✗  {message}", fg=RED_STOP)

    def _render_search_results(self, results):
        self.is_searching = False
        self.public_stations_cache = list(results)

        for i, (name, stn_id) in enumerate(results):
            row = StationRow(
                self.station_frame, name, stn_id, i,
                on_play=self.cmd_play_index,
                on_select=self.cmd_select_index,
            )
            row.pack(fill="x")
            self.station_rows.append(row)
            self._fetch_station_info_for_row(row, name)

        self.station_frame.update_idletasks()
        self.station_canvas.configure(scrollregion=self.station_canvas.bbox("all"))
        self.station_canvas.yview_moveto(0)

        self.search_status.config(
            text=f"  ✓  {len(results)} station(s) found  ·  double-click or press ▶ to play",
            fg=GREEN_ON
        )

    def cmd_select_index(self, index):
        if self.selected_index == index: return
        if 0 <= self.selected_index < len(self.station_rows):
            self.station_rows[self.selected_index].select(False)
        self.selected_index = index
        if 0 <= index < len(self.station_rows):
            self.station_rows[index].select(True)

    def cmd_play_index(self, index):
        if index < 0 or index >= len(self.public_stations_cache): return
        name, stn_id = self.public_stations_cache[index]
        self.cmd_select_index(index)

        self.root.after(0, lambda: self.logo_label.config(image="", text="LOADING\nLOGO..."))
        self.dispatch_req(f"/play_stn?id={stn_id}")

        self._trigger_now_playing_enrichment(name)

    def cmd_init(self):
        threading.Thread(target=self._init_thread, daemon=True).start()

    def _init_thread(self):
        if not self.api_lock.acquire(blocking=False):
            self.ui_log("!!! ERR: Radio is busy.")
            return
        try:
            radio = self.get_radio()
            txt = radio.req("/init?language=en", timeout=10)
            self.is_connected = True
            if txt and "<cur_play_name>" in txt:
                try:
                    name = txt.split("<cur_play_name>")[1].split("</cur_play_name>")[0]
                    self.root.after(0, lambda: self.status.set("CONNECTED", "ok"))
                    self._trigger_now_playing_enrichment(name)
                except IndexError:
                    self.root.after(0, lambda: self.status.set("CONNECTED", "ok"))
            elif txt:
                self.root.after(0, lambda: self.status.set("CONNECTED", "ok"))
            else:
                self.root.after(0, lambda: self.status.set("Connection failed", "error"))
                self.is_connected = False
        finally:
            self.api_lock.release()

    def clear_logs(self):
        self.terminal.config(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.config(state="disabled")
