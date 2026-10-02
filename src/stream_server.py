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

from logsetup import get_logger, setup_logging

log = setup_logging('youtube_stream.server')
log_req = get_logger('server.request')

# Anchor to the project root regardless of the caller's cwd.
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
COOKIES_FILE = DATA_DIR / "cookies" / "youtube_cookies.txt"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cookies").mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def get_ydl_opts(for_video=False):
    """Get yt-dlp options.

    Search uses extract_flat for speed, but flat extraction omits `thumbnail`
    (verified: every entry comes back with thumbnail=None), which leaves the UI
    with blank grey cards. So we synthesise the thumbnail URL from the video id
    instead — i.ytimg.com serves it deterministically for every video.
    """
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    if not for_video:
        opts['extract_flat'] = True  # fast search: metadata only
    if COOKIES_FILE.exists():
        opts['cookies'] = str(COOKIES_FILE)
    return opts


def thumbnail_for(video_id: str) -> str:
    """Deterministic thumbnail URL for a YouTube video id."""
    return f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'


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
                    'thumbnail': e.get('thumbnail') or thumbnail_for(e['id']),
                    'channel': e.get('uploader', 'Unknown'),
                    # GUI (yt_stream.render_grid) reads 'view_count'; emit that name.
                    'view_count': e.get('view_count') or 0,
                    'duration': e.get('duration') or 0,
                })
            result['videos'] = videos
        except Exception as exc:
            result['error'] = str(exc)

    t = threading.Thread(target=_search, daemon=True)
    t.start()
    t.join(timeout=15)

    if t.is_alive():
        log_req.warning('search TIMED OUT after 15s: %r', query)
        return jsonify({'videos': [], 'message': 'Search timed out'}), 200

    if 'error' in result:
        log_req.error('search ERROR for %r: %s', query, result['error'])
        return jsonify(result), 500
    log_req.info('search OK: %r -> %d videos', query, len(result['videos']))
    return jsonify(result)


@app.route('/api/video/<video_id>')
def api_video(video_id):
    """Get direct stream URLs for playback.

    YouTube serves adaptive (DASH) streams: video and audio are SEPARATE
    URLs and no muxed/progressive format is offered. So we must return both,
    otherwise playback is silent. Audio-only entries carry height=None, hence
    the explicit `or 0` when comparing.
    """
    url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        opts = get_ydl_opts(for_video=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats')
        if not formats:
            return jsonify({'error': 'No formats available'}), 500

        # Muxed (audio+video in one) is preferred when a server offers it.
        muxed = [
            f for f in formats
            if f.get('url')
            and f.get('acodec') not in (None, 'none')
            and f.get('vcodec') not in (None, 'none')
        ]
        if muxed:
            best = max(muxed, key=lambda f: f.get('height') or 0)
            return jsonify({
                'id': video_id,
                'title': info.get('title'),
                'url': best.get('url'),
                'audio_url': None,          # already muxed
                'duration': info.get('duration'),
            })

        # Adaptive: pick best video and best audio independently.
        videos = [
            f for f in formats
            if f.get('url') and f.get('vcodec') not in (None, 'none') and f.get('height')
        ]
        audios = [
            f for f in formats
            if f.get('url') and f.get('acodec') not in (None, 'none')
        ]
        if not videos:
            return jsonify({'error': 'No usable video format'}), 500

        best_video = max(videos, key=lambda f: f.get('height') or 0)
        log_req.info('api_video %s: %d formats, video=%sp%s, audio=%s',
                     video_id, len(formats), best_video.get('height'),
                     best_video.get('ext'), 'yes' if audios else 'NO')
        payload = {
            'id': video_id,
            'title': info.get('title'),
            'url': best_video.get('url'),
            'ext': best_video.get('ext'),
            'height': best_video.get('height'),
            'duration': info.get('duration'),
        }
        if audios:
            best_audio = max(
                audios, key=lambda f: f.get('abr') or f.get('tbr') or 0
            )
            payload['audio_url'] = best_audio.get('url')
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/proxy/<video_id>')
def proxy(video_id):
    """Proxy endpoint — opens video player page"""
    import requests
    try:
        resp = requests.get(f'http://127.0.0.1:5000/api/video/{video_id}', timeout=20)
        data = resp.json()
        if 'error' in data:
            return f'<h1>Error: {data["error"]}</h1>', 500
        return render_template_string(
            PLAYER_TEMPLATE,
            video_url=data['url'],
            audio_url=data.get('audio_url'),
            video_title=data.get('title') or '',
        )
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
                    <div class="video-meta">${formatViews(v.view_count)} views</div>
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
<head>
<meta charset="UTF-8">
<title>{{ video_title }}</title>
<style>
  body{margin:0;background:#000;color:#f2f2f2;font-family:system-ui,sans-serif}
  #stage{position:relative;width:100%;height:100vh}
  video{width:100%;height:100%;object-fit:contain;background:#000}
  #bar{position:absolute;left:0;right:0;bottom:0;padding:10px 14px;
       background:linear-gradient(transparent,rgba(0,0,0,.85));display:flex;
       gap:10px;align-items:center}
  #play{background:#cc0000;color:#fff;border:0;padding:6px 14px;border-radius:4px;
        cursor:pointer;font-size:14px}
  #seek{flex:1}
  #time{font-size:12px;color:#ddd;min-width:88px;text-align:right}
</style>
</head>
<body>
<div id="stage">
  <video id="vp" playsinline></video>
  <!-- DASH: audio is a separate stream, played through a hidden audio element
       and kept in sync with the video. -->
  <audio id="ap" preload="auto"{% if not audio_url %} style="display:none"{% endif %}></audio>
  <div id="bar">
    <button id="play">Pause</button>
    <input id="seek" type="range" min="0" max="1000" value="0">
    <span id="time">0:00 / 0:00</span>
  </div>
</div>
<script>
var vp=document.getElementById('vp'), ap=document.getElementById('ap');
var VIDEO_URL={{ video_url|tojson }};
var AUDIO_URL={{ audio_url|tojson }};
vp.src=VIDEO_URL;
if(AUDIO_URL){ ap.src=AUDIO_URL; }

function fmt(s){s=Math.max(0,s|0);var m=(s/60)|0,x=s%60;
  return m+':'+(x<10?'0':'')+x;}

// Keep the audio element locked to the video clock (DASH has no muxed stream).
function sync(){ if(AUDIO_URL && ap.readyState>0) ap.currentTime=vp.currentTime; }
vp.addEventListener('play',function(){ if(AUDIO_URL)ap.play(); });
vp.addEventListener('pause',function(){ if(AUDIO_URL)ap.pause(); });
vp.addEventListener('seeking',sync);
vp.addEventListener('timeupdate',sync);
setInterval(sync,1000);

var seek=document.getElementById('seek'), time=document.getElementById('time');
vp.addEventListener('timeupdate',function(){
  if(vp.duration){ seek.value=vp.currentTime/vp.duration*1000;
    time.textContent=fmt(vp.currentTime)+' / '+fmt(vp.duration); }
});
seek.addEventListener('input',function(){ if(vp.duration) vp.currentTime=seek.value/1000*vp.duration; });
document.getElementById('play').addEventListener('click',function(){
  if(vp.paused){ vp.play(); this.textContent='Pause'; }
  else { vp.pause(); this.textContent='Play'; }
});
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, threaded=True)
