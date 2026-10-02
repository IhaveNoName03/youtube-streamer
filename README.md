# YouTube Stream

Ad-free YouTube streaming with local user accounts and YouTube cookies support.

## What it is

A desktop app that browses and plays YouTube videos without ads, using **yt-dlp** for extraction and **mpv** for playback. User accounts are local (username/password hashed with PBKDF2-SHA256). YouTube cookies can be imported for access to member-only or age-restricted content.

The UI mimics YouTube's grid layout: search, video cards with thumbnails, channel names, view counts, and playback controls.

## Screenshot

Not included yet — run `python3 app.py` to see it.

## Requirements

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Flask](https://flask.palletsprojects.com/) — local proxy server
- [requests](https://requests.readthedocs.io/)
- [pillow](https://python-pillow.org/) — optional, for thumbnails
- [python-mpv](https://github.com/jaseg/python-mpv) + [mpv](https://mpv.io/) — for embedded playback
- [tkinter](https://docs.python.org/3/library/tkinter.html) — usually bundled with Python

## Install

Use a virtualenv. The app must run under an interpreter that has the
dependencies — running bare `python3 app.py` on a system Python fails.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# mpv must also be installed (system package)
# Arch: sudo pacman -S mpv
# Debian/Ubuntu: sudo apt install mpv
# Fedora: sudo dnf install mpv

.venv/bin/python app.py
```

Or use the launcher:

```bash
./start.sh
```

## Accounts

The app starts with **no accounts** — create one from the login screen on first
run. There is deliberately no default account.

If you want the old demo account (`testuser` / `testpass123`) for local
experimentation, construct `UserAuth(create_demo_user=True)`. A shipped default
credential is effectively an unauthenticated backdoor on any machine that isn't
strictly localhost-only.

## Usage

1. Launch the app
2. Create an account or log in
3. Search for videos in the search bar
4. Click a video card to play it in the embedded mpv player
5. Use the playback controls: play/pause (or spacebar), seek bar, volume, speed (0.5x–2.0x), fullscreen, close

### Tabs

- **Browse** — search results grid
- **History** — your watch history (per-user, stored locally, last 200 entries)
- **Playlists** — create playlists, add videos, play in order, delete

### YouTube cookies (premium / restricted content)

1. Export cookies from your browser (e.g. "Get cookies.txt LOCALLY" extension)
2. In the app: **User → Set YouTube Cookies**
3. Select the cookies file
4. The app copies it to `data/cookies/youtube_cookies.txt` and yt-dlp uses it for requests

## Directory structure

```
youtubedl/
├── app.py                         # Entry point
├── start.sh                       # Launcher script
├── requirements.txt               # Python deps
├── README.md
├── diagnostic.py                  # Self-check harness (14 tests)
├── docs/
│   └── UPGRADE_PLAN.md            # Upgrade roadmap
└── src/
    ├── yt_stream.py               # Main Tkinter app (auth, UI, tabs, playback)
    ├── player.py                  # PlaybackController: embedded mpv + controls
    ├── stream_server.py           # Flask proxy server (yt-dlp extraction)
    └── data/
        ├── __init__.py            # Exports: WatchHistory, Playlists, SyncRecommendations
        ├── history.py             # WatchHistory: per-user JSON, dedup, 200-entry cap
        ├── playlists.py           # Playlists: create, add, remove, delete, play-all
        └── recommendations.py     # SyncRecommendations stub
```

Data directory (`data/`):

```
data/
├── users.json                     # User accounts (hashed passwords)
├── cookies/
│   └── youtube_cookies.txt       # YouTube cookies (if imported)
├── downloads/                     # (reserved)
└── users/
    └── <username>/
        ├── history.json           # Watch history
        └── playlists.json         # Playlists
```

## Features

- **Local user accounts** — username/password, PBKDF2-SHA256 hashed, stored in `data/users.json`
- **Ad-free playback** — yt-dlp extracts the direct video URL, mpv plays it (no YouTube ads)
- **Embedded mpv** — player renders inside the Tkinter window, not a separate window
- **Playback controls** — play/pause, seek bar, time display, volume slider, speed (0.5x–2.0x), fullscreen
- **Keyboard shortcuts** — space (play/pause), ←/→ (seek ±5s), ↑/↓ (volume), f (fullscreen), Esc (close)
- **Watch history** — per-user JSON, dedup on re-watch, capped at 200 entries
- **Playlists** — create, add video, play all in order with auto-advance, delete
- **YouTube cookies** — import cookies.txt for premium/restricted content
- **Search** — via local Flask proxy that calls yt-dlp's extractor

## Platform

Linux. Tested on Arch (CachyOS). mpv and tkinter are assumed available.

## Development

Run the diagnostic to verify everything is wired up:

```bash
.venv/bin/python diagnostic.py
```

Expected: 14/14 checks pass.

### Regression tests

```bash
.venv/bin/python -m pytest tests/ -v
```

`tests/test_bugs.py` locks in fixes for previously-found bugs. It replays real
captured yt-dlp responses from `tests/fixtures/`, so it needs no network and
runs in about two seconds. Tests that need a display are skipped automatically
when Tk cannot open one.

### Playback and DASH

YouTube serves adaptive streams: video and audio are separate URLs and no muxed
format is offered. `player.PlaybackController` therefore takes
`build_controls=False` when embedded in the main window, since the app supplies
its own control bar — otherwise two bars render for one video. The browser player
at `/proxy/<id>` plays the audio stream through a synced `<audio>` element.

## Caveats

- This is a personal project, not a YouTube client. It works by extracting video URLs via yt-dlp and playing them with mpv.
- YouTube's Terms of Service may prohibit automated access. Use at your own discretion.
- AI-assisted development — code may need review.

## License

Not specified. Treat as unlicensed / all rights reserved unless you add one.
