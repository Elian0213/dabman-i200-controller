# DABMAN i200 Controller

A modular Python/Tkinter desktop application for controlling the **Imperial DABMAN i200** via its local REST API.

This project implements a custom "Industrial" UI to bypass the native web interface, adding features like high-res logo enrichment via Radio-Browser and real-time ICY metadata extraction from live streams.

## Features

- **High-DPI Support:** Native Windows DPI awareness for sharp text rendering on 4K displays.
- **Metadata Enrichment:** Fetches high-quality station logos and stream URLs from Radio-Browser API.
- **Live Track Info:** Continuous polling of ICY metadata (StreamTitle) directly from audio stream headers.
- **Native Search:** Deep-links into the radio's internal database for station discovery.
- **API Logging:** Integrated terminal showing raw XML/HTTP request/response cycles.
- **Modular Design:** Separation of API logic, custom UI widgets, and theme constants.

## Project Structure

```text
.
├── src/
│   ├── main.py          # Entry point (High-DPI config & Tkinter loop)
│   ├── api/
│   │   └── dabman.py    # DABMANi200 API wrapper
│   └── gui/
│       ├── app.py       # Main application logic
│       ├── widgets.py   # Reusable custom UI components
│       └── constants.py # Palette and Font definitions
├── build.bat            # Windows PyInstaller build script
├── icon.ico             # App icon/favicon
├── requirements.txt
└── .gitignore
```

## Setup

### Prerequisites
- Python 3.13+
- Imperial DABMAN i200 (on the same local network)

### Installation
1. Clone the repository:
   ```bash
   git clone [https://github.com/Elian0213/dabman-i200-controller.git](https://github.com/Elian0213/dabman-i200-controller.git)
   cd dabman-i200-controller
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python src/main.py
   ```

## Building Executable

To compile into a standalone `.exe` (Windows):

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Run the build script:
   ```bash
   ./build.bat
   ```
3. Find the output in `dist/DABMAN_Control.exe`.

## Technical Configuration

- **Theme:** Colors and fonts are managed in `src/gui/constants.py`.
- **Fonts:** Defaulted to **Segoe UI** for UI and **Consolas** for terminal data.
- **API:** Communicates with the radio via port 80 (commands) and 8080 (visuals).
