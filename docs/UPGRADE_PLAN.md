# YouTube Streamer — Upgrade Plan v3 (Final)

## Scope (confirmed)
Full YouTube experience: recommendations, channel browsing, watch history, playlists, playback controls. Per-user local storage for history and playlists.

## What "Recommendations" means (confirmed)
1. **"More like this"**: When viewing a video, show related videos — same channel videos + similar search results
2. **Discovery feed**: Home screen shows a "Popular" feed — search results for broad categories (music, gaming, news, etc.)

## Watch History (confirmed)
- Per-user JSON file: `data/<username>/history.json`
- Stores: video_id, title, channel, watched_at, watch_duration (seconds)
- Shown in a "History" panel/tab
- Clicking a history item resumes playback

## Playlists (confirmed)
- Create playlist (named)
- Add current video to playlist (button in player UI)
- Play all in order, auto-advance to next
- Delete playlist
- Stored in `data/<username>/playlists.json`

## Playback Controls (confirmed)
- Play/pause button
- Seek bar (clickable, shows progress)
- Time display (elapsed / total)
- Volume slider
- Playback speed selector (0.5x, 1x, 1.5x, 2x)
- Fullscreen toggle (mpv handles this via keys)

## Implementation Order

### 1. Playback controls (highest priority)
- Add control bar to player UI
- Integrate with mpv events (playback-time, duration, pause-state, volume)
- Implement seek, volume, speed controls
- Keyboard shortcuts when player focused

### 2. Channel browsing
- Extract channel info from yt-dlp (uploader, channel URL)
- Channel page: show channel name, videos from that channel
- Navigate from video card's channel link

### 3. Watch history
- History module: save/load per-user
- Record watch event on video start/stop
- History panel in UI

### 4. Playlists
- Playlist module: create, list, add, delete
- Add-to-playlist button in player
- Playlist player: iterate through videos

### 5. Recommendations
- "More like this": when video playing, search same channel + search video title
- Discovery feed: pre-populate home with broad searches

### 6. Search improvements
- Debounce, search history, trending default

### 7. Architecture cleanup
- Split into modules: player, history, playlist, channel

---

## Files

| File | Action |
|------|--------|
| `src/player.py` | Create — playback controller, full controls |
| `src/history.py` | Create — watch history module |
| `src/playlist.py` | Create — playlist module |
| `src/channel.py` | Create — channel extraction + browsing |
| `src/yt_stream.py` | Major modify — integrate all modules |
| `requirements.txt` | Modify — any new deps |
