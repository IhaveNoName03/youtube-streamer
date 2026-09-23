# YouTube Streamer

**⚠️ AI Generated Content Notice:** This project was generated with AI assistance. The code, documentation, and structure may require manual review and modification to meet your specific needs.

A clean, YouTube-like streaming application with local user authentication and YouTube cookies support for premium content.

## Features

- **YouTube-like UI**: Clean streaming interface with video grid
- **Local User Accounts**: Secure username/password authentication  
- **YouTube Cookies**: Import cookies for premium content access
- **Proxy-based Streaming**: Uses yt-dlp to access YouTube videos
- **Self-contained**: All data stored in app directory or `~/.local/share/youtubedl/`

## Requirements

- Python 3.8+
- yt-dlp
- Flask
- requests
- pillow (optional - for thumbnail loading)

## Installation

```bash
# Install dependencies
pip install flask yt-dlp requests pillow

# Run directly
python3 app.py
```

## Directory Structure

```
youtubedl/
├── app.py                    # Main entry point
├── README.md
└── src/
    ├── yt_stream.py          # Tkinter GUI application
    └── stream_server.py      # Flask proxy server
```

## Usage

1. Run `python3 app.py`
2. Create an account or login
3. Search for YouTube videos
4. Click a video to play in your browser

## YouTube Cookies (Premium)

1. Export cookies from your browser using "Get YouTube Cookies" extension
2. In the app: User → Set YouTube Cookies
3. Select the cookies file
4. Re-login to YouTube for premium content access

## Configuration

All data is stored in:
- `data/users.json` - User accounts (hashed passwords)
- `data/cookies/youtube_cookies.txt` - YouTube cookies  
- `data/downloads/` - Downloaded files (if any)

---

*This application was generated with AI assistance to provide a starting point for a YouTube streaming app. You may need to customize the styling, features, and security measures for production use.*