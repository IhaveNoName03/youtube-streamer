#!/usr/bin/env python3
"""
YouTube Streaming Proxy Server
Uses yt-dlp to proxy YouTube videos for inline playback
Self-contained: all data stored in app directory
"""

from flask import Flask, request, render_template_string, jsonify
import yt_dlp
import threading
from pathlib import Path

# Get app directory (where this script is located)
APP_DIR = Path(__file__).parent.parent.resolve() if __file__ != __file__ else Path.cwd()
DATA_DIR = APP_DIR / "data"
COOKIES_FILE = DATA_DIR / "cookies" / "youtube_cookies.txt"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cookies").mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def get_ydl_opts():
    """Get yt-dlp options for search (metadata only, no format resolution)"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,  # just metadata, no format info — fast
    }
    if COOKIES_FILE.exists():
        opts['cookies'] = str(COOKIES_FILE)
    return opts


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/search')
def api_search():
    """Search YouTube — runs yt-dlp in a thread with timeout to avoid blocking Flask"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'videos': []})

    result = {'videos': []}

    def _search():
        try:
            opts = get_ydl_opts()
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f'ytsearch25:{query}', download=False)
            entries = info.get('entries', [])
            videos = []
            for e in entries:
                if not e or 'id' not in e:
                    continue
                videos.append({
                    'id': e['id'],
                    'title': e.get('title', 'Untitled'),
                    'thumbnail': e.get('thumbnail', ''),
                    'channel': e.get('uploader', 'Unknown'),
                    'views': e.get('view_count', 0),
                })
            result['videos'] = videos
        except Exception as exc:
            result['error'] = str(exc)

    t = threading.Thread(target=_search, daemon=True)
    t.start()
    t.join(timeout=15)

    if t.is_alive():
        return jsonify({'videos': [], 'message': 'Search timed out'}), 200

    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/video/<video_id>')
def api_video(video_id):
    """Get direct video URL for playback"""
    url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        if COOKIES_FILE.exists():
            opts['cookies'] = str(COOKIES_FILE)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if 'formats' not in info:
            return jsonify({'error': 'No formats available'}), 500

        best = None
        for f in info['formats']:
            if f.get('url') and (f.get('acodec') != 'none' or f.get('vcodec') != 'none'):
                if not best or f.get('height', 0) > best.get('height', 0):
                    best = f
        if not best:
            return jsonify({'error': 'No usable format'}), 500

        return jsonify({'id': video_id, 'title': info.get('title'), 'url': best.get('url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/proxy/<video_id>')
def proxy(video_id):
    """Proxy endpoint — opens video player page"""
    import requests
    try:
        resp = requests.get(f'http://127.0.0.1:5000/api/video/{video_id}', timeout=10)
        data = resp.json()
        if 'error' in data:
            return f'<h1>Error: {data["error"]}</h1>', 500
        return render_template_string(PLAYER_TEMPLATE, video_url=data['url'])
    except Exception as e:
        return f'<h1>Proxy error: {e}</h1>', 500


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Stream</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; color: #f2f2f2;
        }
        .header {
            background: #0f0f0f; padding: 0 20px;
            border-bottom: 1px solid #1a1a1a;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 100;
            height: 52px;
        }
        .header-logo {
            font-size: 18px; font-weight: 700;
            color: #cc0000; letter-spacing: -0.5px;
            display: flex; align-items: center; gap: 8px;
        }
        .header-logo svg { width: 20px; height: 20px; }
        .header-tag {
            font-size: 11px; color: #8a8a8a;
            text-transform: uppercase; letter-spacing: 0.5px;
        }
        .search-bar {
            padding: 12px 20px; background: #0a0a0a;
        }
        .search-container { max-width: 640px; margin: 0 auto; }
        .search-input {
            width: 100%; padding: 10px 16px;
            border-radius: 24px;
            border: 1px solid #232323;
            background: #161616; color: #f2f2f2;
            font-size: 14px;
            transition: border-color 0.15s, background 0.15s;
        }
        .search-input:focus {
            outline: none;
            border-color: #cc0000;
            background: #1a1a1a;
        }
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 10px; padding: 8px 16px 40px;
        }
        .video-card {
            background: #161616; border-radius: 8px;
            cursor: pointer; overflow: hidden;
            border: 1px solid #1a1a1a;
            transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
        }
        .video-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.4);
            border-color: #232323;
        }
        .video-thumb {
            width: 100%; aspect-ratio: 16/9;
            background: #232323;
            background-size: cover;
            background-position: center;
            position: relative;
        }
        .video-duration {
            position: absolute; bottom: 6px; right: 6px;
            background: rgba(0,0,0,0.85); color: #f2f2f2;
            font-size: 11px; font-weight: 500;
            padding: 2px 4px; border-radius: 3px;
        }
        .video-info { padding: 8px 10px 10px; }
        .video-title {
            font-size: 13px; font-weight: 500;
            line-height: 1.35; margin-bottom: 4px;
            display: -webkit-box; -webkit-line-clamp: 2;
            -webkit-box-orient: vertical; overflow: hidden;
            color: #f2f2f2;
        }
        .video-channel {
            font-size: 11px; color: #8a8a8a;
            margin-bottom: 2px;
        }
        .video-meta { font-size: 11px; color: #8a8a8a; }
        .empty-state {
            text-align: center; padding: 60px 20px;
            color: #8a8a8a;
        }
        .empty-state h3 { font-size: 16px; margin-bottom: 8px; color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-logo">
            <svg viewBox="0 0 24 22" fill="currentColor"><path d="M10,8 L7.5,6.5 L10,5 L12.5,7.5 L12,8 L10,8 M2,10 L4.5,12.5 L2,15 L4,15 L4,13.5 L7.5,10 L4.5,10 L4,8.5 L2,8 L3.5,6.5 L5,8 L3.5,8.5 L3.5,10 L2,10 M14,15 L14,8 L16,8 L16,7.5 L12,7.5 L12,8 L13.5,10 L15.5,12 L13.5,14 L14,15 M22,10 L19.5,7.5 L22,5 L19.5,5 L19,6 L17,8 L16,6.5 L17,5 L20,5 L22,8 L19.5,10 L17,12.5 L19.5,15 L20,15 L20,13.5 L22,10 Z"/></svg>
            Stream
        </div>
        <div class="header-tag">ad-free &bull; embedded</div>
    </div>
    <div class="search-bar">
        <div class="search-container">
            <input type="text" id="searchInput" class="search-input" placeholder="Search YouTube..." autofocus>
        </div>
    </div>
    <div id="videoContainer" class="video-grid"></div>
    <script>
        function formatViews(c){ return c>=1e6?(c/1e6).toFixed(1)+'M':c>=1e3?(c/1e3).toFixed(1)+'K':c; }
        function renderVideos(){
            const c=document.getElementById('videoContainer');
            const v=window.currentVideos||[];
            if(!v.length){
c.innerHTML='<div class="empty-state"><h3>No results</h3><p>Try a different search</p></div>';
                return;
            }
            c.innerHTML=v.map(v=>`<div class="video-card" onclick="openVideo('${v.id}')">
                <div class="video-thumb" style="background-image:url('${v.thumbnail||''}')">
                    <span class="video-duration"></span>
                </div>
                <div class="video-info">
                    <div class="video-title">${v.title}</div>
                    <div class="video-channel">${v.channel}</div>
                    <div class="video-meta">${formatViews(v.views)} views</div>
                </div>
            </div>`).join('');
        }
        document.getElementById('searchInput').addEventListener('keypress',e=>{
            if(e.key==='Enter'){ const q=e.target.value.trim(); if(!q) return;
                fetch('/api/search?q='+encodeURIComponent(q)).then(r=>r.json()).then(d=>{
                    window.currentVideos=d.videos||[];
                    renderVideos();
                });
            }
        });
        function openVideo(id){ window.open('/proxy/'+id,'_blank'); }
    </script>
</body>
</html>
"""

PLAYER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><style>body{margin:0;background:#000}video{width:100%;height:100vh;object-fit:contain}</style></head>
<body><video id="vp" controls autoplay><source src="{{ video_url }}" type="video/mp4"></video></body>
<script>document.getElementById('vp').src="{{ video_url }}";</script></html>
"""

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, threaded=True)
