"""
Playback Controller
Full playback controls for the embedded mpv player:
- Play/pause
- Seek bar
- Time display (elapsed / total)
- Volume control
- Playback speed
- Fullscreen toggle
"""

import tkinter as tk
from tkinter import ttk
import mpv
from typing import Optional, Callable, Any


class PlaybackController:
    """Manages mpv playback with full UI controls"""
    
    def __init__(self, container: tk.Widget, on_close: Optional[Callable] = None):
        """
        Args:
            container: Tkinter widget to embed mpv into
            on_close: function to call when player should close
        """
        self.container = container
        self.on_close = on_close
        self.player: Optional[Any] = None
        self.video_url: Optional[str] = None
        self.video_title: Optional[str] = None
        
        self._create_ui()
    
    def _create_ui(self) -> None:
        """Create the playback control UI"""
        # Player container (for mpv to render into)
        self.mpv_container = tk.Frame(self.container, bg='black')
        self.mpv_container.pack(fill='both', expand=True)
        
        # Control bar at bottom
        self.control_bar = tk.Frame(self.container, bg='#282828', height=50)
        self.control_bar.pack(fill='x', side='bottom')
        self.control_bar.pack_propagate(False)
        
        # Play/Pause button
        self.play_btn = tk.Button(self.control_bar, text="⏸", width=3,
                                  command=self.toggle_play_pause,
                                  bg='#4a90d9', fg='white',
                                  font=('Segoe UI', 12, 'bold'),
                                  relief='flat', cursor='hand2')
        self.play_btn.pack(side='left', padx=10)
        
        # Time display
        self.time_label = tk.Label(self.control_bar, text="0:00 / 0:00",
                                   font=('Segoe UI', 10),
                                   bg='#282828', fg='#cccccc')
        self.time_label.pack(side='left', padx=10)
        
        # Seek bar
        self.seek_bar = ttk.Scale(self.control_bar, from_=0, to=100,
                                  orient='horizontal',
                                  command=self._on_seek_change)
        self.seek_bar.pack(fill='x', side='left', expand=True, padx=(10, 5))
        self.seek_bar.set(0)
        self.seek_bar.configure(state='disabled')  # Enabled when playing
        
        # Volume control
        tk.Label(self.control_bar, text="🔊", bg='#282828', fg='white',
                font=('Segoe UI', 12)).pack(side='left', padx=(5, 0))
        self.volume_slider = ttk.Scale(self.control_bar, from_=0, to=100,
                                        orient='horizontal',
                                        command=self._on_volume_change)
        self.volume_slider.set(100)
        self.volume_slider.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        # Playback speed
        self.speed_var = tk.StringVar(value="1.0x")
        speed_menu = tk.OptionMenu(self.control_bar, self.speed_var,
                                   "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x",
                                   command=self._on_speed_change)
        speed_menu.config(bg='#4a90d9', fg='white', relief='flat',
                         font=('Segoe UI', 9), highlightthickness=0)
        speed_menu["menu"].config(bg='#282828', fg='white')
        speed_menu.pack(side='left', padx=(5, 10))
        
        # Fullscreen toggle
        self.fullscreen_btn = tk.Button(self.control_bar, text="⛶",
                                        command=self.toggle_fullscreen,
                                        bg='#282828', fg='white',
                                        font=('Segoe UI', 10, 'bold'),
                                        relief='flat', cursor='hand2')
        self.fullscreen_btn.pack(side='left', padx=(0, 10))
        
        # Close button
        self.close_btn = tk.Button(self.control_bar, text="✕ Close",
                                   command=self.close,
                                   bg='#f44336', fg='white',
                                   font=('Segoe UI', 10, 'bold'),
                                   relief='flat', cursor='hand2')
        self.close_btn.pack(side='right', padx=(0, 10))
        
        # Keyboard bindings
        self._setup_keybindings()
    
    def _setup_keybindings(self):
        """Setup keyboard shortcuts for the player"""
        self.container.bind('<space>', lambda e: self.toggle_play_pause())
        self.container.bind('<Left>', lambda e: self.seek(-5))
        self.container.bind('<Right>', lambda e: self.seek(5))
        self.container.bind('<Up>', lambda e: self.set_volume(
            min(100, self.volume_slider.get() + 10)))
        self.container.bind('<Down>', lambda e: self.set_volume(
            max(0, self.volume_slider.get() - 10)))
        self.container.bind('f', lambda e: self.toggle_fullscreen())
        self.container.bind('Escape', lambda e: self._on_esc())
    
    def _on_esc(self):
        """Escape key handler"""
        if self.player and self.player.pause:
            self.toggle_play_pause()
        else:
            self.close()
    
    def _on_seek_change(self, value):
        """Handle seek bar drag"""
        if self.player and self.player.duration > 0:
            pos = float(value) / 100 * self.player.duration
            self.player.seek = pos
    
    def _on_volume_change(self, value):
        """Handle volume slider"""
        vol = float(value) / 100
        if self.player:
            self.player.volume = vol
    
    def _on_speed_change(self, value):
        """Handle playback speed change"""
        speed = float(value.replace('x', ''))
        if self.player:
            self.player.playback_rate = speed
    
    def load(self, url: str, title: Optional[str] = None) -> None:
        """
        Load a video for playback.
        
        Args:
            url: YouTube URL or direct video URL
            title: Display title for the video
        """
        self.video_url = url
        self.video_title = title
        
        # Destroy previous player
        if self.player:
            try:
                self.player.quit()
            except Exception:
                pass
        
        # Get window ID for embedding
        self.container.update_idletasks()
        window_id = self.mpv_container.winfo_id()
        
        if window_id == 0:
            # Widget not realized yet, delay
            self.container.after(100, lambda: self.load(url, title))
            return
        
        # Create mpv player
        try:
            self.player = mpv.MPV(
                wid=str(window_id),
                ytdl=True,
                ytdl_hook_enabled=True,
                keep_open=False,
                pause=False,
                idle=False,
                force_window=True,
                no_terminal=True,
                video=True,
                audio=True,
                cache=30,
                demuxer_max_bytes=1024*1024*1024,  # 1GB cache
            )
            
            # Bind events
            self.player.bind('playback-time', self._on_playback_time)
            self.player.bind('duration', self._on_duration)
            self.player.bind('pause', self._on_pause)
            self.player.bind('idle', self._on_idle)
            
            # Start playback
            self.player.play(url)
            self.play_btn.config(text="⏸")
            self.seek_bar.configure(state='normal')
            
        except Exception as e:
            print(f"Playback error: {e}")
            if self.on_close:
                self.on_close()
    
    def _on_playback_time(self, event, value):
        """Update seek bar and time display"""
        if self.player and self.player.duration > 0:
            pct = (value / self.player.duration) * 100
            self.seek_bar.set(pct)
            self.time_label.config(
                text=f"{self._format_time(value)} / {self._format_time(self.player.duration)}")
    
    def _on_duration(self, event, value):
        """Update time display when duration is known"""
        if value > 0:
            self.time_label.config(text=f"0:00 / {self._format_time(value)}")
    
    def _on_pause(self, event, value):
        """Update play button icon"""
        if value:
            self.play_btn.config(text="▶")
        else:
            self.play_btn.config(text="⏸")
    
    def _on_idle(self, event, value):
        """Called when playback ends"""
        if value:
            if self.on_close:
                self.on_close()
    
    def toggle_play_pause(self) -> None:
        """Toggle play/pause"""
        if self.player:
            if self.player.pause:
                self.player.pause = False
            else:
                self.player.pause = True
    
    def seek(self, seconds: float) -> None:
        """Seek by seconds (positive = forward, negative = backward)"""
        if self.player and self.player.duration > 0:
            new_pos = self.player.playback_time + seconds
            new_pos = max(0, min(new_pos, self.player.duration))
            self.player.seek = new_pos
    
    def set_volume(self, value: float) -> None:
        """Set volume (0-100)"""
        vol = value / 100
        if self.player:
            self.player.volume = vol
        self.volume_slider.set(value)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen (mpv handles this)"""
        if self.player:
            # Toggle mpv's fullscreen
            current = self.player.fullscreen
            self.player.fullscreen = not current
    
    def close(self):
        """Close playback and cleanup"""
        if self.player:
            try:
                self.player.quit()
            except Exception:
                pass
            self.player = None
        
        # Clear UI
        for widget in self.container.winfo_children():
            widget.destroy()
        
        if self.on_close:
            self.on_close()
    
    def _format_time(self, seconds):
        """Format seconds as M:SS or H:MM:SS"""
        if seconds < 0:
            return "0:00"
        seconds = int(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    def is_playing(self):
        """Check if currently playing"""
        return self.player is not None and not self.player.pause
    
    def is_paused(self):
        """Check if paused"""
        return self.player is not None and self.player.pause
