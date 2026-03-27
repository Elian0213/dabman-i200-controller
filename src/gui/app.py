# src/gui/app.py
import tkinter as tk
import urllib.parse
import threading
import io
import re
import requests
from PIL import Image, ImageTk

from api.dabman import DABMANi200
from .constants import *
from .widgets import PanelLabel, IndustrialEntry, IndustrialButton, StatusIndicator, StationRow, sep

class App:
    def __init__(self, root):
        self.root = root
        self.radio = None
        self.is_connected = False

        # Data caches
        self.public_stations_cache = []
        self.station_rows: list[StationRow] = []
        self.selected_index = -1

        # Now Playing State
        self.current_station_name = ""
        self.current_stream_url = None
        self.has_hi_res_logo = False

        self.api_lock = threading.Lock()
        self.current_vol = 5
        self.is_searching = False
        self.loading_frame = 0

        self.root.title("DABMAN i200  ·  CONTROL")
        self.root.geometry("1150x780")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self._build_title_bar()
        self._build_body()

        # Background workers
        self._poll_radio_logo()
        self._poll_current_track()

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

    # ── Universal Radio-Browser & ICY Lookup ──────────────────────────────────
    def _lookup_radio_browser(self, station_name):
        """Reusable function to fetch high-res logo bytes and stream URL."""
        try:
            url = "https://de1.api.radio-browser.info/json/stations/search"
            params = {
                "name": station_name,
                "order": "clickcount",
                "reverse": "true",
                "limit": 5,
                "hidebroken": "true"
            }
            resp = requests.get(url, params=params, timeout=5,
                                headers={"User-Agent": "DABMANControl/1.0 gibas.nl"})

            if resp.status_code == 200:
                data = resp.json()
                if data:
                    best_station = next((s for s in data if s.get("favicon")), data[0])
                    favicon_url = best_station.get("favicon")
                    stream_url = best_station.get("url_resolved") or best_station.get("url")

                    logo_bytes = None
                    if favicon_url:
                        if favicon_url.startswith("//"):
                            favicon_url = "https:" + favicon_url
                        try:
                            img_headers = {"User-Agent": "Mozilla/5.0"}
                            img_resp = requests.get(favicon_url, timeout=5, headers=img_headers)
                            if img_resp.status_code == 200 and img_resp.content:
                                logo_bytes = img_resp.content
                        except Exception as e:
                            print(f"Failed to download image from {favicon_url}: {e}")

                    return logo_bytes, stream_url
        except Exception as e:
            print(f"Radio-browser lookup failed for {station_name}: {e}")
        return None, None

    def _get_icy_metadata(self, stream_url):
        """Extracts current playing song from audio stream."""
        try:
            headers = {'Icy-MetaData': '1', 'User-Agent': 'VLC/3.0.9 LibVLC/3.0.9'}
            with requests.get(stream_url, headers=headers, stream=True, timeout=3) as r:
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

    # ── Now Playing Enrichment ────────────────────────────────────────────────
    def _trigger_now_playing_enrichment(self, station_name):
        """Fetches high-res logo and track for the currently playing station."""
        self.current_station_name = station_name
        self.has_hi_res_logo = False # Reset flag until we find one
        self.current_stream_url = None

        self.now_playing_stn_lbl.config(text=station_name)
        self.now_playing_trk_lbl.config(text="Locating stream info...")

        def task():
            logo_bytes, stream_url = self._lookup_radio_browser(station_name)

            # 1. Set Hi-Res Logo
            if logo_bytes:
                self.has_hi_res_logo = True # Prevents radio from overwriting with low-res logo
                try:
                    image = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
                    image.thumbnail((130, 130), Image.Resampling.LANCZOS)
                    # Create background plate
                    bg_img = Image.new("RGBA", (130, 130), GROOVE)
                    ox = (130 - image.width) // 2
                    oy = (130 - image.height) // 2
                    bg_img.paste(image, (ox, oy), image)

                    photo = ImageTk.PhotoImage(bg_img)
                    self.root.after(0, self._update_main_logo_ui, photo)
                except Exception:
                    pass

            # 2. Set Stream URL and trigger immediate track lookup
            if stream_url:
                self.current_stream_url = stream_url
                track = self._get_icy_metadata(stream_url)
                if track:
                    self.root.after(0, self.now_playing_trk_lbl.config, {"text": f"♫ {track}"})
                else:
                    self.root.after(0, self.now_playing_trk_lbl.config, {"text": "Live Broadcast"})
            else:
                self.root.after(0, self.now_playing_trk_lbl.config, {"text": "No stream data available"})

        threading.Thread(target=task, daemon=True).start()

    def _poll_current_track(self):
        """Runs continuously in background to update the live track text."""
        def task():
            if self.current_stream_url:
                track = self._get_icy_metadata(self.current_stream_url)
                if track:
                    self.root.after(0, self.now_playing_trk_lbl.config, {"text": f"♫ {track}"})

        threading.Thread(target=task, daemon=True).start()
        self.root.after(10000, self._poll_current_track) # Poll every 10 seconds

    def _poll_radio_logo(self):
        """Fallback: Fetches low-res logo from the hardware radio if no hi-res is found."""
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

    # ── Station Row Enrichment ────────────────────────────────────────────────
    def _fetch_station_info_for_row(self, row: StationRow, station_name: str):
        """Populates the search list rows."""
        def task():
            logo_bytes, stream_url = self._lookup_radio_browser(station_name)

            if logo_bytes:
                self.root.after(0, row.set_logo, logo_bytes)

            if stream_url:
                track_name = self._get_icy_metadata(stream_url)
                if track_name:
                    self.root.after(0, row.set_track, f"♫ {track_name}")
                else:
                    self.root.after(0, row.set_track, "Radio Stream Live")
            else:
                self.root.after(0, row.set_track, "Stream info unavailable")

        threading.Thread(target=task, daemon=True).start()

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
        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=14)
        tk.Label(right, text="gibas.nl", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 7), pady=4).pack()
        sep(self.root)

    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        left_col = tk.Frame(body, bg=BG, width=280)
        left_col.pack(side="left", fill="y", expand=False)
        left_col.pack_propagate(False)

        mid_col = tk.Frame(body, bg=BG, width=360)
        mid_col.pack(side="left", fill="both", expand=False, padx=(14, 0))
        mid_col.pack_propagate(False)

        right_col = tk.Frame(body, bg=BG)
        right_col.pack(side="right", fill="both", expand=True, padx=(14, 0))

        self._build_left(left_col)
        self._build_mid(mid_col)
        self._build_right(right_col)

    def _build_left(self, col):
        # ── 1. Network ────────────────────────────────────────────────────────
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

        # ── 2. Now Playing ────────────────────────────────────────────────────
        tk.Frame(col, bg=BG, height=14).pack()
        PanelLabel(col, "Now Playing").pack(fill="x", pady=(0, 6))

        # Main Logo
        logo_wrap = tk.Frame(col, bg=BORDER, width=140, height=140)
        logo_wrap.pack()
        logo_wrap.pack_propagate(False)
        self.logo_label = tk.Label(
            logo_wrap, bg=GROOVE,
            text="NO LOGO", fg=TEXT_DIM, font=FONT_LABEL, justify="center"
        )
        self.logo_label.pack(fill="both", expand=True, padx=1, pady=1)

        # Station Name & Track below logo
        self.now_playing_stn_lbl = tk.Label(col, text="---", bg=BG, fg=TEXT, font=FONT_STATION)
        self.now_playing_stn_lbl.pack(fill="x", pady=(8, 2))

        self.now_playing_trk_lbl = tk.Label(col, text="Ready", bg=BG, fg=ACCENT_GLOW, font=FONT_STATION2)
        self.now_playing_trk_lbl.pack(fill="x", pady=(0, 16)) # Extra padding before controls

        # ── 3. Playback & Audio Controls ──────────────────────────────────────
        ctrl_outer = tk.Frame(col, bg=PANEL)
        ctrl_outer.pack(fill="x", pady=2)

        ctrl_row = tk.Frame(ctrl_outer, bg=PANEL)
        ctrl_row.pack(fill="none", expand=True, padx=10, pady=8)

        # Stop Button
        IndustrialButton(ctrl_row, text="■ STOP",
                         command=lambda: self.dispatch_req("/stop"),
                         accent=RED_STOP, accent_dark=RED_DARK, width=8).pack(side="left", padx=(0, 16))

        # Volume Controls
        tk.Label(ctrl_row, text="VOL", bg=PANEL, fg=TEXT_DIM,
                 font=FONT_LABEL, anchor="e").pack(side="left", padx=(0, 4))
        IndustrialButton(ctrl_row, text="−", command=self.cmd_vol_down, width=2).pack(side="left", padx=2)
        self.vol_label = tk.Label(ctrl_row, text=str(self.current_vol),
                                  bg=GROOVE, fg=ACCENT, font=FONT_MONO, width=3)
        self.vol_label.pack(side="left", padx=4)
        IndustrialButton(ctrl_row, text="+", command=self.cmd_vol_up, width=2).pack(side="left", padx=2)

    def _build_mid(self, col):
        PanelLabel(col, "Station Search  ·  Radio-Browser DB").pack(fill="x", pady=(0, 8))

        search_row = tk.Frame(col, bg=BG)
        search_row.pack(fill="x", pady=(0, 8))
        self.pub_search_ent = IndustrialEntry(search_row, width=20)
        self.pub_search_ent.insert(0, "NPO")
        self.pub_search_ent.pack(side="left", padx=(0, 6), fill="y")
        self.pub_search_ent.entry.bind("<Return>", lambda e: self.cmd_search())
        IndustrialButton(search_row, text="SEARCH", command=self.cmd_search, width=9).pack(side="left")

        list_outer = tk.Frame(col, bg=BORDER, bd=1)
        list_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_outer, bg=PANEL, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                                 command=canvas.yview, bg=PANEL2, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        canvas.config(yscrollcommand=scrollbar.set)

        self.station_frame = tk.Frame(canvas, bg=PANEL)
        self.station_frame_id = canvas.create_window((0, 0), window=self.station_frame, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self.station_frame_id, width=canvas.winfo_width())

        self.station_frame.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(
            self.station_frame_id, width=e.width))

        def _on_scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_scroll)

        self.station_canvas = canvas

        self.search_status = tk.Label(col, text="No search yet", bg=BG, fg=TEXT_DIM,
                                      font=FONT_LABEL, anchor="w")
        self.search_status.pack(fill="x", pady=(4, 0))

        tk.Frame(col, bg=BG, height=4).pack()
        IndustrialButton(col, text="▶  PLAY SELECTED", command=self.cmd_play_selected,
                         accent=GREEN_ON, accent_dark=GREEN_DIM, width=22).pack(anchor="e")

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

        scrollbar = tk.Scrollbar(term_frame, command=self.terminal.yview,
                                 bg=PANEL, troughcolor=BG)
        scrollbar.pack(side="right", fill="y")
        self.terminal.config(yscrollcommand=scrollbar.set)

        tk.Frame(col, bg=BG, height=6).pack()
        IndustrialButton(col, text="CLEAR", command=self.clear_logs,
                         accent=STEEL, width=10).pack(anchor="e")

    # ── Actions ───────────────────────────────────────────────────────────────
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
        if not self.is_searching:
            return
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
        self.public_stations_cache.clear()
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
                    name   = name_match.group(1)
                    name   = name.replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')
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

        self.search_status.config(
            text=f"  ✓  {len(results)} station(s) found  ·  double-click or press ▶ to play",
            fg=GREEN_ON
        )

    def cmd_select_index(self, index):
        if self.selected_index == index:
            return
        if 0 <= self.selected_index < len(self.station_rows):
            self.station_rows[self.selected_index].select(False)
        self.selected_index = index
        if 0 <= index < len(self.station_rows):
            self.station_rows[index].select(True)

    def cmd_play_index(self, index):
        if index < 0 or index >= len(self.public_stations_cache):
            return
        name, stn_id = self.public_stations_cache[index]
        self.cmd_select_index(index)
        self.root.after(0, lambda: self.status.set(f"Playing  ›  {name[:20]}", "playing"))
        self.root.after(0, lambda: self.logo_label.config(image="", text="LOADING\nLOGO..."))
        self.dispatch_req(f"/play_stn?id={stn_id}")

        # Trigger the enrichment specifically for the new station
        self._trigger_now_playing_enrichment(name)

    def cmd_play_selected(self):
        self.cmd_play_index(self.selected_index)

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
                    self.root.after(0, lambda: self.status.set(f"Playing  ›  {name}", "playing"))
                    self._trigger_now_playing_enrichment(name)
                except IndexError:
                    self.root.after(0, lambda: self.status.set("Connected  ·  Idle", "ok"))
            elif txt:
                self.root.after(0, lambda: self.status.set("Connected  ·  Idle", "ok"))
            else:
                self.root.after(0, lambda: self.status.set("Connection failed", "error"))
                self.is_connected = False
        finally:
            self.api_lock.release()

    def clear_logs(self):
        self.terminal.config(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.config(state="disabled")
