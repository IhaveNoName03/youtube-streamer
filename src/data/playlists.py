#!/usr/bin/env python3
"""
Playlists Module
User playlist management: create, add, remove, delete, play all
"""

import json
from pathlib import Path


class Playlists:
    """Manage user playlists"""
    
    def __init__(self, user_dir: Path):
        user_dir.mkdir(parents=True, exist_ok=True)
        self.file = user_dir / "playlists.json"
        self._load()
    
    def _load(self):
        if self.file.exists():
            try:
                with open(self.file) as f:
                    self.playlists = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.playlists = {}
        else:
            self.playlists = {}
    
    def save(self) -> None:
        with open(self.file, 'w') as f:
            json.dump(self.playlists, f, indent=2)
        self.file.chmod(0o600)
    
    def create(self, name: str) -> tuple[bool, str]:
        """Create a new playlist"""
        if name in self.playlists:
            return False, "Playlist already exists"
        self.playlists[name] = []
        self.save()
        return True, "Created"
    
    def delete(self, name: str) -> bool:
        """Delete a playlist"""
        if name in self.playlists:
            del self.playlists[name]
            self.save()
            return True
        return False
    
    def add_video(self, playlist_name: str, video: dict) -> tuple[bool, str]:
        """Add a video to a playlist"""
        if playlist_name not in self.playlists:
            return False, "Playlist not found"
        for v in self.playlists[playlist_name]:
            if v.get('id') == video.get('id'):
                return False, "Already in playlist"
        self.playlists[playlist_name].append(video)
        self.save()
        return True, "Added"
    
    def remove_video(self, playlist_name: str, video_id: str) -> tuple[bool, str]:
        """Remove a video from a playlist"""
        if playlist_name not in self.playlists:
            return False, "Playlist not found"
        self.playlists[playlist_name] = [
            v for v in self.playlists[playlist_name] if v.get('id') != video_id
        ]
        self.save()
        return True, "Removed"
    
    def get(self, name: str) -> list:
        """Get all videos in a playlist"""
        return self.playlists.get(name, [])
    
    def list(self) -> list[str]:
        """List all playlist names"""
        return list(self.playlists.keys())
    
    def clear(self, name: str) -> bool:
        """Clear all videos from a playlist"""
        if name in self.playlists:
            self.playlists[name] = []
            self.save()
            return True
        return False


# Convenience function
def get_playlists(user_dir: Path) -> Playlists:
    return Playlists(user_dir)