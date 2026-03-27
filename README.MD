# DABMAN i400 API Test Console

A Python-based desktop application for controlling and testing the Imperial DABMAN i400 internet radio via its local REST API.

This project provides a custom, industrial-styled Tkinter UI that allows you to trigger API commands, manage presets, control playback, and view raw XML/text responses in a built-in terminal.

## Features

* **Real-Time Status Indicators:** Visual feedback for network connection and current playback state.
* **Comprehensive API Coverage:** Test zero-parameter lists (System Info, Fav Lists, Status) and parameterized actions (SendKey, Play Station, Volume/Mute).
* **Built-in API Terminal:** View, scroll, and clear raw HTTP responses directly in the app without needing a separate CLI window. Large XML responses are automatically truncated to maintain UI performance.
* **Custom Industrial UI:** A sleek, dark-mode interface built purely with standard Tkinter (no external UI libraries required).

## Prerequisites

* **Python 3.13+**
* The radio and your computer must be on the same local network.
* Ensure you know the local IP address of your DABMAN i400 device.

## Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Elian0213/dabman-i200-controller.git](https://github.com/Elian0213/dabman-i200-controller.git)
   cd dabman-i400-controller
