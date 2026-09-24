#!/usr/bin/env python3
"""
Watch History Module
Per-user watch history storage
"""

import json
from pathlib import Path
from datetime import datetime


class WatchHistory:
    """Track watch history for a user"""
    
    def __init__(self, user_dir: Path):
        user_dir.mkdir(parents=True, exist_ok=True)
        self.file = user_dir / "history.json"
        self._load()
    
    def _load(self):
        if self.file.exists():
            try:
                with open(self.file) as f:
                    self.entries = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.entries = []
        else:
            self.entries = []
    
    def save(self) -> None:
        with open(self.file, 'w') as f:
            json.dump(self.entries, f, indent=2)
        self.file.chmod(0o600)
    
    def add(self, video_id: str, title: str, channel: str, duration: int = 0):
        """Add or update a video in history"""
        for entry in self.entries:
            if entry['video_id'] == video_id:
                entry['watched_at'] = datetime.now().isoformat()
                entry['watch_duration'] = max(entry.get('watch_duration', 0), duration)
                self.save()
                return
        
        self.entries.insert(0, {
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'watched_at': datetime.now().isoformat(),
            'watch_duration': duration
        })
        self.entries = self.entries[:200]
        self.save()
    
    def get(self, limit: int = 50) -> list:
        """Get watch history entries"""
        return self.entries[:limit]
    
    def get_by_id(self, video_id: str) -> dict | None:
        """Get a specific entry by video ID"""
        for entry in self.entries:
            if entry['video_id'] == video_id:
                return entry
        return None
    
    def clear(self):
        """Clear all history"""
        self.entries = []
        self.save()
    
    def remove(self, video_id: str):
        """Remove a specific video from history"""
        self.entries = [e for e in self.entries if e['video_id'] != video_id]
        self.save()


# Convenience function for creating a history instance
def get_history(user_dir: Path) -> WatchHistory:
    return WatchHistory(user_dir)