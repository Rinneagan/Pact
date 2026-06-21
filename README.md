# Pact

A premium, secure desktop application for searching, previewing, downloading, and reading PDF files. The application is built on a modern hybrid stack: a robust **Python backend** (for API coordination, file processing, and local database stores) bound to a stunning **HTML5/CSS3/JavaScript frontend** with a glassmorphic aesthetic served locally via **`pywebview`**.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

---

## 🎨 Core Premium Features

### 🖥️ Glassmorphic Wallpaper Theme Manager
* Customize your ambient desktop environment with three curated abstract themes: **Neon Waves**, **Cyberpunk Mist**, and **Aurora Glow**.
* Synchronizes with Light/Dark theme triggers, instantly updating panel transparency and activating `backdrop-filter: blur(25px) saturate(180%)` to blend panels into backgrounds.
* Saves wallpaper choices inside the client's `localStorage` to preserve layout appearance across sessions.

### 📚 Embedded PDF Reader & Dark Theme Inversion
* Fully integrated PDF viewer powered by PyMuPDF (`fitz`), rendering crisp pages directly inside the web window with advanced zoom and pagination.
* Features **Dynamic Color Inversion**: when Dark Theme is enabled, PDF page color profiles are instantly inverted on the fly via Pillow (`ImageOps.invert`) to match dark mode styles.
* Fast outline extraction (Table of Contents) and related local document suggestion index.

### 📅 GitHub-Style Reading Heatmap
* Visualizes your daily reading metrics over a rolling 30-week (210 days) calendar grid of glowing, green contribution cubes.
* Calculates pages read dynamically, tracking stats without invasive alert or nag mechanics.

### 🧘 Distraction-Free Focus Mode
* Enters Focus Mode with a simple key bind (`Esc` to exit) or toolbar trigger.
* Collapses sidebars, auto-slides the reader toolbar out of view (revealed with top-edge hover), and overlays floating zen dashboards.

### 🌧️ Zen Soundscapes Floating Panel
* Plays loopable, royalty-free background ambient soundscapes (**Rain**, **Forest Birds**, and **Lofi Beats**) to facilitate deep focus.
* Features smooth volume sliders and fading transitions (800ms-1s) when starting audio, changing tracks, or exiting Focus Mode.
* Operates fully offline relative to local audio assets to bypass WebView CORS and network restrictions.

### ⏱️ Glassmorphic Pomodoro Study Timer
* Floating countdown timer featuring a circular SVG progress ring that fills in sync with the countdown duration.
* Select Focus (25m), Break (5m), or Rest (15m) sessions with custom dropdown selections.
* Automatically pauses active Zen Audio loops during breaks to encourage physical rest, and resumes them during Focus periods.
* Play elegant dual-tone chime alarms synthesized completely offline using the **Web Audio API**.

### 🏆 Confetti-Triggered Daily Reading Goals
* Configure a daily page target (e.g. 15 pages) directly inside the Reading Log dashboard.
* Updates progress indicators in real-time as pages are read.
* Triggers a physics-based, offline canvas confetti explosion when the daily goal is reached.

### 🏷️ Local PDF Keyword Cloud
* Extracts the top 25 high-frequency terms from PDF documents on loading, filtering common English stopwords.
* Displays words as custom weighted tags in the sidebar. Clicking any keyword instantly populates page badges mapping to that keyword.

---

## ⚙️ Architecture & Project Structure

The project has been refactored to separate the UI layer from Python core operations, communicating via `pywebview`'s JSON-RPC bridge API.

```
Pact/
├── config.py           # Application settings (timeouts, size caps, directories)
├── crawler.py          # Backend PDF crawler (SerpApi wrapper, document validations)
├── app.py              # Main coordinator & JSON-RPC Bridge API (PactAPI)
├── requirements.txt    # Python package dependencies
├── .env                 # API configuration keys (not in git)
├── persistence/        # Python JSON persistence stores
│   ├── __init__.py
│   └── stores.py       # Progress, recent searches, tag, stats, and bookmark stores
├── web/                # HTML5 frontend files served by pywebview
│   ├── index.html      # Main layout, stats tab, reader view, and panels
│   ├── main.js         # Async controller bindings, Pomodoro timers, and Canvas confetti
│   ├── style.css       # Glassmorphism tokens, heatmap grid, and animations
│   └── audio/          # Local royalty-free loop assets (rain, lofi, birds)
└── assets/             # Branding logs and font assets
```

### Bridge API Methods ([app.py](app.py))
`app.py` exposes the `PactAPI` class to the frontend context, allowing JavaScript to call:
* `search(query)`: Query PDFs via the crawler.
* `download(url, title)`: Enqueue a file for background download.
* `get_page_image(filepath, page_num, zoom, dark_mode)`: Retrieve base64 page renderings.
* `get_today_pages_read()`: Retrieve current daily reading totals.
* `get_heatmap_data()`: Extract pages read logged over the past 30 weeks.
* `get_keywords(filepath)`: Extract top terms for the keyword cloud.

---

## 🚀 Installation & Setup

### Prerequisites
* Python 3.8 or higher
* Internet connection (for initial PDF search)
* SerpApi API Key ([Get one here](https://serpapi.com/))

### Installation
1. **Clone the repository**
   ```bash
   git clone https://github.com/Rinneagan/Pact.git
   cd Pact
   ```
2. **Install requirements**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure API key**
   Create a `.env` file in the root directory:
   ```bash
   SERPAPI_KEY=your_serpapi_api_key_here
   ```

### Running the App
Launch the desktop application via:
```bash
python app.py
```
