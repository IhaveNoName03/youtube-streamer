#!/usr/bin/env python3
"""
YouTube Streaming Proxy Server
Uses yt-dlp to proxy YouTube videos for inline playback
Self-contained: all data stored in app directory
"""

from flask import Flask, Response, request, render_template_string, jsonify
import yt_dlp
import json
import os
import re
from pathlib import Path

# Get app directory (where this script is located)
APP_DIR = Path(__file__).parent.parent.resolve() if __file__ != __file__ else Path.cwd()
DATA_DIR = APP_DIR / "data"
COOKIES_FILE = DATA_DIR / "cookies" / "youtube_cookies.txt"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cookies").mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# HTML template for the streaming interface (clean YouTube-like design)
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
            background: #181818; color: #fff; 
        }
        .header {
            background: #090909; padding: 12px 20px; 
            border-bottom: 1px solid #303030;
            position: sticky; top: 0; z-index: 100;
        }
        .header h1 { font-size: 18px; font-weight: 500; }
        .search-bar {
            padding: 16px 20px; background: #090909;
        }
        .search-container { display: flex; gap: 8px; }
        .search-input {
            flex: 1; padding: 10px 14px;
            border-radius: 24px; border: 1px solid #303030;
            background: #181818; color: #fff; border: none;
            font-size: 14px; width: 100%;
        }
        .search-input:focus { outline: 2px solid #4a90d9; }
        .search-btn {
            background: #4a90d9; border: none; color: #fff;
            padding: 10px 20px; border-radius: 24px;
            cursor: pointer; font-size: 14px;
        }
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 12px; padding: 16px 20px;
        }
        .video-card {
            background: #181818; border-radius: 8px;
            cursor: pointer; overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .video-card:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .video-thumb {
            width: 100%; aspect-ratio: 16/9;
            background: #303030;
            background-size: cover;
            background-position: center;
        }
        .video-info { padding: 10px 12px; }
        .video-title {
            font-size: 14px; font-weight: 500;
            line-height: 1.4; margin-bottom: 4px;
            display: -webkit-box; -webkit-line-clamp: 2;
            -webkit-box-orient: vertical; overflow: hidden;
        }
        .video-meta { font-size: 12px; color: #888888; }
    </style>
</head>
<body>
    <div class="header"><h1>🎬 YouTube Stream</h1></div>
    <div class="search-bar">
        <div class="search-container">
            <input type="text" id="searchInput" class="search-input" placeholder="Search YouTube...">
            <button class="search-btn" onclick="search()">Search</button>
        </div>
    </div>
    <div id="videoContainer" class="video-grid"></div>
    <script>
        function formatViews(c){ return c>=1e6?(c/1e6).toFixed(1)+'M':c>=1e3?(c/1e3).toFixed(1)+'K':c; }
        function renderVideos(){
            const c=document.getElementById('videoContainer');
            const v=window.currentVideos||[];
            if(!v.length){c.innerHTML='<div style="padding:40px;text-align:center">No videos</div>';return;}
            c.innerHTML='<div class="video-grid">'+v.map(v=>`<div class="video-card" onclick="openVideo('${v.id}')">
                <div class="video-thumb" style="background-image:url('${v.thumbnail}')"></div>
                <div class="video-info"><div class="video-title">${v.title}</div>
                <div class="video-meta">${v.channel} • ${formatViews(v.views)}</div></div></div>`).join('')+'</div>';
        }
        function search(){
            const q=document.getElementById('searchInput').value.trim();
            if(!q) return;
            fetch('/api/search?q='+encodeURIComponent(q)).then(r=>r.json()).then(d=>{
                window.currentVideos=d.videos||[];
                renderVideos();
            });
        }
        function openVideo(id){ window.open('/proxy/'+id,'_blank'); }
        document.getElementById('searchInput').addEventListener('keypress',e=>{if(e.key==='Enter')search();});
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


def get_ydl_opts():
    """Get yt-dlp options"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'bestvideo+bestaudio/best'
    }
    if COOKIES_FILE.exists():
        opts['cookies'] = str(COOKIES_FILE)
    return opts


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'videos': []})
    
    try:
        opts = get_ydl_opts()
        opts.update({'default_search': 'ytsearch', 'max_results': 50})
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f'ytsearch50:{query}', download=False)
        
        videos = [{
            'id': e['id'],
            'title': e.get('title', 'Unknown'),
            'thumbnail': e.get('thumbnail', ''),
            'channel': e.get('uploader', 'Unknown'),
            'views': e.get('view_count', 0)
        } for e in info.get('entries', []) if e and 'id' in e]
        
        return jsonify({'videos': videos})
    except Exception as e:
        return jsonify({'error': str(e), 'videos': []})


@app.route('/api/video/<video_id>')
def api_video(video_id):
    """Get direct video URL"""
    url = f'https://www.youtube.com/watch?v={video_id}'
    opts = get_ydl_opts()
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Get best format URL
        if 'formats' in info:
            best = None
            for f in info['formats']:
                if f.get('url') and (f.get('acodec') != 'none' or f.get('vcodec') != 'none'):
                    if not best or f.get('height', 0) > best.get('height', 0):
                        best = f
        else:
            return jsonify({'error': 'No formats'}), 500
        
        return jsonify({'id': video_id, 'title': info.get('title'), 'url': best.get('url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/proxy/<video_id>')
def proxy(video_id):
    """Proxy endpoint - opens video in page"""
    import requests
    try:
        resp = requests.get(f'http://127.0.0.1:5000/api/video/{video_id}', timeout=10)
        data = resp.json()
        if 'error' in data:
            return f'<h1>Error: {data["error"]}</h1>', 500
        return render_template_string(PLAYER_TEMPLATE, video_url=data['url'])
    except Exception as e:
        return f'<h1>Proxy error: {e}</h1>', 500


@app.route('/api/playlist/<playlist_id>')
def playlist(playlist_id):
    """Get playlist videos"""
    url = f'https://www.youtube.com/playlist?list={playlist_id}'
    opts = get_ydl_opts()
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        videos = [{
            'id': e['id'],
            'title': e.get('title', 'Unknown'),
            'thumbnail': e.get('thumbnail', ''),
            'channel': e.get('uploader', 'Unknown'),
            'views': e.get('view_count', 0)
        } for e in info.get('entries', []) if e and 'id' in e]
        
        return jsonify({'title': info.get('title', 'Unknown'), 'videos': videos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, threaded=True)