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


# Events (as opposed to properties) arrive via the single event_callback slot,
# so they need dispatching by hand.
_EVENT_HANDLERS: dict = {}


class MpvHandle:
    """Compatibility wrapper around mpv.MPV for python-mpv 1.x.

    python-mpv 1.0 removed 0.x's ``MPV.bind(name, callback)`` and its
    ``bind_event`` twin. Properties still work as plain attribute get/set
    (verified: pause, volume, duration, playback-time, fullscreen, filename),
    so the ONLY gap is event/property subscriptions.

    This wrapper restores ``bind(name, callback)`` with the 0.x
    ``callback(event, value)`` signature:
      * property names  -> observe_property
      * event names     -> a single event_callback dispatcher

    Keeping the surface identical means yt_stream.py needs no changes.
    """

    def __init__(self, **options):
        self._mpv = mpv.MPV(**options)
        self._property_handlers: dict = {}
        self._event_handlers: dict = {}
        self._mpv.event_callback = self._dispatch_event
        # mirror the 1.x attribute surface (play, quit, command, ...)
        self.__dict__['_exposed'] = True

    # --- 0.x-compatible bind() -------------------------------------------
    def bind(self, name: str, callback: Callable) -> None:
        """Subscribe to a property or event. 0.x signature."""
        if name in _EVENT_NAMES:
            self._event_handlers[name] = callback
            return

        def _handler(_prop, value):
            try:
                callback(name, value)
            except Exception:
                import logging
                logging.getLogger('youtube_stream.player').exception(
                    'handler for %r raised', name)

        self._property_handlers[name] = callback
        self._mpv.observe_property(name, _handler)

    def _dispatch_event(self, name, data) -> None:
        cb = self._event_handlers.get(name)
        if cb:
            try:
                cb(name, data)
            except Exception:
                import logging
                logging.getLogger('youtube_stream.player').exception(
                    'event handler for %r raised', name)

    # --- delegate everything else to the real handle ----------------------
    def __getattr__(self, item):
        return getattr(self._mpv, item)

    def __setattr__(self, key, value):
        if key in ('_mpv', '_property_handlers', '_event_handlers', '_exposed'):
            object.__setattr__(self, key, value)
        else:
            setattr(self._mpv, key, value)


# mpv event names (as opposed to properties) that the app subscribes to.
_EVENT_NAMES = {'idle', 'end-file', 'shutdown', 'seeked', 'dequeue',
                'video-reconfig', 'audio-reconfig', 'file-loaded',
                'playback-restart'}


# Palette (matches yt_stream.py)
SURFACE  = '#161616'
ELEVATED = '#232323'
MUTED    = '#8a8a8a'
WHITE    = '#f2f2f2'
ACCENT   = '#cc0000'


class PlaybackController:
    """Manages mpv playback, optionally with its own UI controls.

    Set `build_controls=False` when embedding into a host UI that already
    provides a control bar (yt_stream does this). Without it you get two
    stacked control bars for a single video.
    """

    def __init__(self, container: tk.Widget, on_close: Optional[Callable] = None,
                 build_controls: bool = True):
        """
        Args:
            container: Tkinter widget to embed mpv into
            on_close: function to call when player should close
            build_controls: create the built-in control bar. False when the
                host UI supplies its own.
        """
        self.container = container
        self.on_close = on_close
        self.build_controls = build_controls
        self.player: Optional[Any] = None
        self.video_url: Optional[str] = None
        self.video_title: Optional[str] = None

        self._create_ui()

    def _create_ui(self) -> None:
        """Create the playback control UI"""
        # Player container (for mpv to render into)
        self.mpv_container = tk.Frame(self.container, bg='black')
        self.mpv_container.pack(fill='both', expand=True)

        if not self.build_controls:
            # Host UI owns the chrome; expose the attributes it may bind to so
            # callers get a consistent surface.
            self.control_bar = None
            self.play_btn = None
            self.time_label = None
            self.seek_bar = None
            self.volume_slider = None
            self.speed_var = None
            return

        # Control bar at bottom
        self.control_bar = tk.Frame(self.container, bg=ELEVATED, height=50)
        self.control_bar.pack(fill='x', side='bottom')
        self.control_bar.pack_propagate(False)

        # Play/Pause button
        self.play_btn = tk.Button(self.control_bar, text="⏸", width=3,
                                  command=self.toggle_play_pause,
                                  bg=ACCENT, fg=WHITE,
                                  font=('Segoe UI', 12, 'bold'),
                                  relief='flat', cursor='hand2')
        self.play_btn.pack(side='left', padx=10)

        # Time display
        self.time_label = tk.Label(self.control_bar, text="0:00 / 0:00",
                                   font=('Segoe UI', 10),
                                   bg=ELEVATED, fg=WHITE)
        self.time_label.pack(side='left', padx=10)

        # Seek bar
        self.seek_bar = ttk.Scale(self.control_bar, from_=0, to=100,
                                  orient='horizontal',
                                  command=self._on_seek_change)
        self.seek_bar.pack(fill='x', side='left', expand=True, padx=(10, 5))
        self.seek_bar.set(0)
        self.seek_bar.configure(state='disabled')  # Enabled when playing

        # Volume control
        tk.Label(self.control_bar, text="🔊", bg=ELEVATED, fg=WHITE,
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
        speed_menu.config(bg=ACCENT, fg=WHITE, relief='flat',
                         font=('Segoe UI', 9), highlightthickness=0)
        speed_menu["menu"].config(bg=SURFACE, fg=WHITE)
        speed_menu.pack(side='left', padx=(5, 10))

        # Fullscreen toggle
        self.fullscreen_btn = tk.Button(self.control_bar, text="⛶",
                                        command=self.toggle_fullscreen,
                                        bg=SURFACE, fg=WHITE,
                                        font=('Segoe UI', 10, 'bold'),
                                        relief='flat', cursor='hand2')
        self.fullscreen_btn.pack(side='left', padx=(0, 10))

        # Close button
        self.close_btn = tk.Button(self.control_bar, text="✕ Close",
                                   command=self.close,
                                   bg=ACCENT, fg=WHITE,
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
        if self.player and self.player.duration > 0 and self.build_controls:
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
    
    def load(self, url: str, title: Optional[str] = None,
             audio_url: Optional[str] = None) -> None:
        """
        Load a video for playback.

        Args:
            url: a direct media URL, or a YouTube watch URL
            title: Display title for the video
            audio_url: separate audio stream. YouTube serves DASH, so video and
                audio are distinct URLs; mpv takes them as a
                "video://…" + "audio://…" pair.

        Note: mpv only resolves YouTube URLs when its ytdl_hook.lua script is
        installed, which this system's mpv package does not ship. Callers must
        therefore hand us direct stream URLs (see yt_stream._resolve_streams).
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
            self.container.after(100, lambda: self.load(url, title, audio_url))
            return
        
        # Create mpv player.
        # NOTE: do not pass `idle` here. On mpv 0.41 + python-mpv, setting
        # idle=False shuts the core down during construction, so every
        # subsequent call raises "libmpv core has been shutdown" and playback
        # never starts. Verified by isolating each option: wid, keep_open,
        # pause and force_window are all fine; idle is fatal.
        try:
            self.player = MpvHandle(
                wid=str(window_id),
                keep_open=False,
                pause=False,
                force_window=True,
            )
            
            # Bind events
            self.player.bind('playback-time', self._on_playback_time)
            self.player.bind('duration', self._on_duration)
            self.player.bind('pause', self._on_pause)
            self.player.bind('idle', self._on_idle)

            # Start playback. With DASH, video and audio are separate
            # streams, and python-mpv 1.x's play() takes one filename.
            #
            # Verified against the live stream:
            #   loadfile(video, replace) + loadfile(audio, append) -> NO AUDIO
            #   play(video) + audio_add(audio)                  -> AAC AUDIO
            # `append` queues a second *file*; it does not attach the audio
            # track of an already-playing file.
            #
            # NB: plain URLs only. A "video://" / "audio://" track prefix
            # silences playback here — verified: plain plays, prefixed does not.
            if audio_url:
                self.player.play(url)
                try:
                    self.player.audio_add(audio_url)
                except Exception:
                    import logging
                    logging.getLogger('youtube_stream.player').exception(
                        'audio_add failed for %s', url[:60])
            else:
                self.player.play(url)
            if self.build_controls:
                self.play_btn.config(text="⏸")
                self.seek_bar.configure(state='normal')

        except Exception as e:
            print(f"Playback error: {e}")
            if self.on_close:
                self.on_close()
    
    def _on_playback_time(self, event, value):
        """Update seek bar and time display"""
        # observe_property fires once with None before the file is loaded.
        if value is None:
            return
        if self.player and self.player.duration > 0 and self.build_controls:
            pct = (value / self.player.duration) * 100
            self.seek_bar.set(pct)
            self.time_label.config(
                text=f"{self._format_time(value)} / {self._format_time(self.player.duration)}")

    def _on_duration(self, event, value):
        """Update time display when duration is known"""
        # observe_property delivers None until the file is parsed.
        if value and value > 0 and self.build_controls:
            self.time_label.config(text=f"0:00 / {self._format_time(value)}")

    def _on_pause(self, event, value):
        """Update play button icon"""
        if not self.build_controls:
            return
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
        if self.build_controls:
            self.volume_slider.set(value)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen (mpv handles this)"""
        if self.player:
            # Toggle mpv's fullscreen
            current = self.player.fullscreen
            self.player.fullscreen = not current
    
    def close(self):
        """Close playback and cleanup"""
        # Re-entrancy guard: close() calls on_close(), and the host's on_close
        # handler (yt_stream.close_player) calls close() straight back. Without
        # this, any load failure recursed until RecursionError.
        if getattr(self, '_closing', False):
            return
        self._closing = True
        try:
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
        finally:
            self._closing = False
    
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
