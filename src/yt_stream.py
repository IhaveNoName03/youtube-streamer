#!/usr/bin/env python3
"""
YouTube Streaming App - Full YouTube-like experience
Features: Search, video grid, channel browsing, watch history, playlists
Ad-free playback via embedded mpv
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import json
import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import io

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests', '-q'],
                   check=True, stdout=subprocess.DEVNULL)
    import requests

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from player import PlaybackController
    HAS_PLAYER = True
except ImportError:
    HAS_PLAYER = False
    print("Warning: player module not found")

try:
    from data import WatchHistory, Playlists, SyncRecommendations
    HAS_DATA_MODULES = True
except ImportError:
    HAS_DATA_MODULES = False
    print("Warning: data modules not available")

# ============================================================================
# CONFIG
# ============================================================================

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent.resolve()

DATA_DIR = APP_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
COOKIES_FILE = DATA_DIR / "cookies" / "youtube_cookies.txt"
DOWNLOADS_DIR = DATA_DIR / "downloads"
SERVER_SCRIPT = APP_DIR / "src" / "stream_server.py"

SERVER_URL = "http://127.0.0.1:5000"

for d in [DATA_DIR, DATA_DIR / "cookies", DOWNLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# AUTH
# ============================================================================

class UserAuth:
    """Manage local user accounts with password hashing"""

    def __init__(self) -> None:
        self.users: Dict[str, Any] = {}
        self.current_user: Optional[str] = None
        self.load_users()

    def load_users(self) -> None:
        if USERS_FILE.exists():
            try:
                with open(USERS_FILE) as f:
                    self.users = json.load(f)
            except Exception:
                self.users = {}

    def save_users(self) -> None:
        with open(USERS_FILE, 'w') as f:
            json.dump(self.users, f, indent=2)

    def hash_password(self, password: str) -> str:
        """Hash password using PBKDF2-SHA256 with random salt"""
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return salt.hex() + ':' + key.hex()

    def verify_password(self, stored: str, provided: str) -> bool:
        """Verify password against stored hash"""
        try:
            salt, key = stored.split(':')
            new_key = hashlib.pbkdf2_hmac(
                'sha256', provided.encode(),
                bytes.fromhex(salt), 100000
            )
            return new_key.hex() == key
        except (ValueError, KeyError):
            return False

    def create_user(self, username: str, password: str) -> tuple[bool, str]:
        """Create a new user account"""
        if username in self.users:
            return False, "Username already exists"
        self.users[username] = {
            'password': self.hash_password(password),
            'created': datetime.now().isoformat(),
            'yt_authenticated': False
        }
        self.save_users()
        return True, "User created successfully"

    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate user with password"""
        if username not in self.users:
            return False
        return self.verify_password(
            self.users[username]['password'], password
        )

    def delete_user(self, username: str) -> bool:
        """Delete a user account"""
        if username in self.users:
            del self.users[username]
            self.save_users()
            return True
        return False

    def get_user_dir(self, username: str) -> Path:
        """Get per-user data directory"""
        udir = DATA_DIR / "users" / username
        udir.mkdir(parents=True, exist_ok=True)
        return udir


# ============================================================================
# MAIN APP
# ============================================================================

class YouTubeStreamApp:
    """Main YouTube streaming application with Tkinter UI"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("YouTube Stream")
        self.root.geometry("1400x900")
        self.root.configure(bg='#181818')

        self.auth = UserAuth()
        self.current_videos: List[Dict] = []
        self.server = None
        self.current_video: Optional[Dict] = None
        self.search_history: List[str] = []
        self.player = None

        self.create_widgets()
        self.start_server()
        self.show_login()

    def create_widgets(self) -> None:
        """Create main UI widgets"""
        self.main = tk.Frame(self.root, bg='#181818')
        self.main.pack(fill='both', expand=True, padx=24, pady=24)

        header = tk.Frame(self.main, bg='#090909', height=56)
        header.pack(fill='x')
        tk.Label(
            header, text="🎬 YouTube Stream",
            font=('Segoe UI', 18, 'bold'),
            bg='#090909', fg='white'
        ).pack(pady=14)

        search = tk.Frame(self.main, bg='#181818')
        search.pack(fill='x', pady=(0, 24))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search, textvariable=self.search_var,
            font=('Segoe UI', 14), bg='#282828', fg='white',
            insertbackground='white', relief='flat'
        )
        self.search_entry.pack(side='left', fill='x', expand=True, padx=(0, 12))
        self.search_entry.bind('<Return>', lambda e: self.search())

        tk.Button(
            search, text="Search", command=self.search,
            bg='#4a90d9', fg='white', font=('Segoe UI', 12, 'bold'),
            relief='flat'
        ).pack(side='right')

        self.content_frame = tk.Frame(self.main, bg='#181818')
        self.content_frame.pack(fill='both', expand=True)

        self.tab_frame = tk.Frame(self.main, bg='#282828')
        self.tab_frame.pack(fill='x', pady=(0, 0))

        self.tabs: Dict[str, tk.Button] = {}
        for i, (name, cmd) in enumerate([
            ("Browse", self.show_browse),
            ("History", self.show_history),
            ("Playlists", self.show_playlists)
        ]):
            btn = tk.Button(
                self.tab_frame, text=name, command=cmd,
                bg='#282828' if i > 0 else '#4a90d9',
                fg='white' if i > 0 else 'white',
                font=('Segoe UI', 10, 'bold' if i == 0 else 'normal'),
                relief='flat', cursor='hand2'
            )
            btn.pack(side='left', padx=5)
            self.tabs[name] = btn

        self.active_tab = "Browse"

        self.grid = tk.Frame(self.content_frame, bg='#181818')

        self.status = tk.Label(
            self.main, text="Ready",
            font=('Segoe UI', 10),
            bg='#181818', fg='#888888'
        )
        self.status.pack(side='bottom', anchor='w', padx=24, pady=(24, 0))

        self.create_menu()

    def create_menu(self) -> None:
        """Create application menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        user_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="User", menu=user_menu)
        user_menu.add_command(label="Manage Accounts", command=self.manage_accounts)
        user_menu.add_separator()
        user_menu.add_command(label="Set YouTube Cookies", command=self.set_cookies)
        user_menu.add_separator()
        user_menu.add_command(label="Logout", command=self.show_login)

        tools = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools)
        tools.add_command(label="Clear History", command=self.clear_history)
        tools.add_command(label="Clear All Playlists", command=self.clear_playlists)
        tools.add_command(label="Open Config", command=lambda: subprocess.run(
            ['xdg-open', str(DATA_DIR)]
        ))

    def start_server(self) -> None:
        """Start Flask proxy server in background thread"""
        def run() -> None:
            try:
                subprocess.Popen(
                    [sys.executable, str(SERVER_SCRIPT)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"Server start failed: {e}")

        threading.Thread(target=run, daemon=True).start()
        self.check_server()

    def check_server(self) -> None:
        """Check if server is responsive"""
        try:
            requests.get(SERVER_URL, timeout=2)
            self.status.config(text="Connected")
        except Exception:
            self.status.config(text="Connecting...")
            self.root.after(500, self.check_server)

    def search(self) -> None:
        """Trigger search with current query"""
        query = self.search_var.get().strip()
        if not query:
            return

        self.search_history.insert(0, query)
        if len(self.search_history) > 10:
            self.search_history = self.search_history[:10]

        self.current_videos = []
        self.status.config(text=f"Searching: {query}...")

        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query: str) -> None:
        """Perform search via Flask API"""
        try:
            resp = requests.get(
                f'{SERVER_URL}/api/search',
                params={'q': query}, timeout=10
            )
            data = resp.json()
            videos = data.get('videos', [])

            self.root.after(0, lambda: self._render_search_results(videos, query))
        except Exception as e:
            self.root.after(0, lambda: self.status.config(text=f"Error: {e}"))

    def _render_search_results(self, videos: List[Dict], query: str) -> None:
        """Render search results in grid"""
        self.current_videos = videos
        for w in self.content_frame.winfo_children():
            w.destroy()
        self.grid.pack(fill='both', expand=True)
        self.render_grid()
        self.status.config(text=f"Found {len(videos)} videos for '{query}'")

    def render_grid(self) -> None:
        """Render video grid with thumbnails and titles"""
        for w in self.grid.winfo_children():
            w.destroy()

        if not self.current_videos:
            tk.Label(
                self.grid, text="No videos found",
                fg='#888888', bg='#181818', font=('Segoe UI', 14)
            ).pack(expand=True)
            return

        for i, v in enumerate(self.current_videos):
            r, c = i // 4, i % 4

            card = tk.Frame(
                self.grid, bg='#282828', relief='flat', cursor='hand2'
            )
            card.grid(row=r, column=c, padx=12, pady=12, sticky='nsew')

            thumb = tk.Frame(card, bg='#303030', height=180, width=320)
            thumb.pack()
            thumb.grid_propagate(False)

            if HAS_PIL and v.get('thumbnail'):
                try:
                    resp = requests.get(v['thumbnail'], timeout=3)
                    img = Image.open(io.BytesIO(resp.content)).resize((320, 180))
                    tk_img = ImageTk.PhotoImage(img)
                    lbl = tk.Label(thumb, image=tk_img, bg='#303030')
                    lbl.image = tk_img
                    lbl.pack(expand=True, fill='both')
                except Exception:
                    pass

            tk.Label(
                card, text=v.get('title', 'Unknown')[:80],
                font=('Segoe UI', 10), bg='#282828', fg='white',
                wraplength=300
            ).pack(padx=12, pady=6)

            views = v.get('view_count', 0)
            vs = (
                f"{views/1e6:.1f}M" if views >= 1e6
                else f"{views/1e3:.1f}K" if views >= 1e3
                else str(views)
            )
            tk.Label(
                card, text=f"{v.get('channel', 'Unknown')} • {vs} views",
                font=('Segoe UI', 9), bg='#282828', fg='#888888'
            ).pack(padx=12, pady=(0, 12))

            card.bind('<Button-1>', lambda e, vid=v: self.play_video(vid))

        for i in range(4):
            self.grid.grid_columnconfigure(i, weight=1)

    def _init_player_ui(self, video: Dict) -> None:
        """Initialize player UI elements"""
        self.player_canvas = tk.Canvas(
            self.content_frame, bg='black', bd=0, highlightthickness=0
        )
        self.player_canvas.pack(fill='both', expand=True)

        info_bar = tk.Frame(self.content_frame, bg='#1a1a1a')
        info_bar.pack(fill='x', pady=(0, 0))
        tk.Label(
            info_bar, text=video.get('title', 'Unknown'),
            font=('Segoe UI', 11, 'bold'),
            bg='#1a1a1a', fg='white'
        ).pack(side='left', padx=10)
        tk.Label(
            info_bar, text=video.get('channel', 'Unknown'),
            font=('Segoe UI', 9),
            bg='#1a1a1a', fg='#888888'
        ).pack(side='left', padx=(0, 10))

        self.control_bar = tk.Frame(self.content_frame, bg='#282828', height=60)
        self.control_bar.pack(fill='x')
        self.control_bar.pack_propagate(False)

        self.play_btn = tk.Button(
            self.control_bar, text="⏸", width=3,
            command=self.toggle_play_pause,
            bg='#4a90d9', fg='white', font=('Segoe UI', 14, 'bold'),
            relief='flat', cursor='hand2'
        )
        self.play_btn.pack(side='left', padx=10)

        self.time_lbl = tk.Label(
            self.control_bar, text="0:00 / 0:00",
            font=('Segoe UI', 10), bg='#282828', fg='#cccccc'
        )
        self.time_lbl.pack(side='left', padx=10)

        self.seek_var = tk.DoubleVar()
        self.seek_bar = ttk.Scale(
            self.control_bar, from_=0, to=100,
            variable=self.seek_var, orient='horizontal',
            command=self._on_seek_drag
        )
        self.seek_bar.pack(fill='x', side='left', expand=True, padx=(10, 5))

        tk.Label(
            self.control_bar, text="🔊", bg='#282828', fg='white',
            font=('Segoe UI', 12)
        ).pack(side='left', padx=(5, 2))
        self.volume_var = tk.DoubleVar(value=100)
        self.volume_bar = ttk.Scale(
            self.control_bar, from_=0, to=100,
            variable=self.volume_var, orient='horizontal',
            command=self._on_volume_change
        )
        self.volume_bar.pack(side='left', fill='x', expand=True, padx=(0, 5))

        self.speed_var = tk.StringVar(value="1.0x")
        self.speed_menu = tk.OptionMenu(
            self.control_bar, self.speed_var,
            "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x",
            command=self._on_speed_change
        )
        self.speed_menu.config(
            bg='#4a90d9', fg='white', relief='flat',
            font=('Segoe UI', 9), highlightthickness=0, width=5
        )
        self.speed_menu["menu"].config(bg='#282828', fg='white')
        self.speed_menu.pack(side='left', padx=(0, 10))

        tk.Button(
            self.control_bar, text="⛶", command=self.toggle_fullscreen,
            bg='#282828', fg='white', font=('Segoe UI', 10, 'bold'),
            relief='flat', cursor='hand2'
        ).pack(side='left', padx=(0, 5))

        tk.Button(
            self.control_bar, text="+ Playlist", command=self.add_to_playlist,
            bg='#282828', fg='white', font=('Segoe UI', 9),
            relief='flat', cursor='hand2'
        ).pack(side='left', padx=(0, 10))

        tk.Button(
            self.control_bar, text="✕ Close", command=self.close_player,
            bg='#f44336', fg='white', font=('Segoe UI', 10, 'bold'),
            relief='flat', cursor='hand2'
        ).pack(side='right', padx=(0, 10))

    def init_mpv(self, video: Dict) -> None:
        """Initialize mpv player after UI is ready"""
        if not HAS_PLAYER:
            tk.Label(
                self.player_canvas, text="mpv not available",
                font=('Segoe UI', 14), bg='black', fg='white'
            ).pack(expand=True)
            return

        self.player_canvas.update_idletasks()
        window_id = self.player_canvas.winfo_id()

        if window_id == 0:
            self.root.after(100, lambda: self.init_mpv(video))
            return

        try:
            self.player = PlaybackController(
                self.player_canvas,
                on_close=self.close_player
            )
            self.player.load(
                f'https://www.youtube.com/watch?v={video.get("id")}',
                video.get('title', 'Unknown')
            )
            self.player.player.bind('playback-time', self._update_time)
            self.player.player.bind('duration', self._update_duration)
            self.player.player.bind('pause', self._update_play_state)
            self.player.player.bind('idle', self._on_idle)

        except Exception as e:
            messagebox.showerror("Playback Error", str(e))
            self.close_player()

    def _update_time(self, event: Any, value: float) -> None:
        if self.player and hasattr(self.player, 'player') and \
           self.player.player and self.player.player.duration > 0:
            self.seek_var.set(value / self.player.player.duration * 100)
            self.time_lbl.config(
                text=f"{self._fmt(value)} / {self._fmt(self.player.player.duration)}"
            )

    def _update_duration(self, event: Any, value: float) -> None:
        if value > 0:
            self.time_lbl.config(text=f"0:00 / {self._fmt(value)}")

    def _update_play_state(self, event: Any, value: bool) -> None:
        self.play_btn.config(text="▶" if value else "⏸")

    def _on_idle(self, event: Any, value: bool) -> None:
        if value:
            self.root.after(500, self.close_player)

    def _on_seek_drag(self, value: str) -> None:
        if self.player and self.player.player.duration > 0:
            self.player.player.seek = \
                float(value) / 100 * self.player.player.duration

    def _on_volume_change(self, value: str) -> None:
        if self.player:
            self.player.player.volume = float(value) / 100

    def _on_speed_change(self, value: str) -> None:
        if self.player:
            self.player.player.playback_rate = float(value.replace('x', ''))

    def toggle_play_pause(self) -> None:
        """Toggle play/pause state"""
        if self.player:
            self.player.player.pause = not self.player.player.pause

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode"""
        if self.player:
            self.player.player.fullscreen = not self.player.player.fullscreen

    def seek(self, seconds: float) -> None:
        """Seek video by seconds"""
        if self.player and self.player.player.duration > 0:
            new = self.player.player.playback_time + seconds
            self.player.player.seek = max(0, min(new, self.player.player.duration))

    def close_player(self) -> None:
        """Close current player and return to browse"""
        if hasattr(self, 'player') and self.player:
            self.player.close()
            self.player = None

        for w in self.content_frame.winfo_children():
            w.destroy()

        self.show_browse()
        self.status.config(text="Ready")

        if self.current_video:
            user_dir = self.auth.get_user_dir(self.auth.current_user or "guest")
            history = WatchHistory(user_dir)
            history.add(
                self.current_video.get('id'),
                self.current_video.get('title', ''),
                self.current_video.get('channel', '')
            )
            self.current_video = None

    def _fmt(self, seconds: float) -> str:
        """Format seconds as H:MM:SS or M:SS"""
        if seconds < 0:
            return "0:00"
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def add_to_playlist(self) -> None:
        """Add current video to a playlist"""
        if not self.current_video:
            return

        if not self.auth.current_user:
            messagebox.showinfo(
                "Login Required", "Please log in to use playlists"
            )
            return

        user_dir = self.auth.get_user_dir(self.auth.current_user)
        playlists = Playlists(user_dir)

        dlg = tk.Toplevel(self.root)
        dlg.title("Add to Playlist")
        dlg.geometry("300x200")
        dlg.configure(bg='#181818')
        dlg.grab_set()

        tk.Label(
            dlg, text="Create or select playlist:",
            font=('Segoe UI', 11),
            bg='#181818', fg='white'
        ).pack(pady=10)

        tk.Label(
            dlg, text="Playlist name:",
            font=('Segoe UI', 10),
            bg='#181818', fg='#888888'
        ).pack()
        name_entry = tk.Entry(dlg, font=('Segoe UI', 11), bg='#1e1e1e', fg='white')
        name_entry.pack(fill='x', padx=20, pady=5)

        existing = playlists.list()
        if existing:
            tk.Label(
                dlg, text="Or select existing:",
                font=('Segoe UI', 10),
                bg='#181818', fg='#888888'
            ).pack()
            lb = tk.Listbox(dlg, bg='#1e1e1e', fg='white', height=4)
            for n in existing:
                lb.insert(tk.END, n)
            lb.pack(fill='x', padx=20, pady=5)

        def do_add() -> None:
            name = name_entry.get().strip()
            if not name:
                sel = lb.curselection()
                if sel:
                    name = lb.get(sel[0])
                else:
                    messagebox.showerror("Error", "Playlist name required")
                    return

            ok, msg = playlists.add_video(name, self.current_video)
            if ok:
                messagebox.showinfo("Success", f"Added to '{name}'")
                dlg.destroy()
            else:
                messagebox.showerror("Error", msg)

        tk.Button(
            dlg, text="Add", command=do_add,
            bg='#4caf50', fg='white', font=('Segoe UI', 11, 'bold')
        ).pack(pady=15, padx=30)
        dlg.bind('<Return>', lambda e: do_add())

    def show_browse(self) -> None:
        """Show browse tab with video grid"""
        self.active_tab = "Browse"
        for name, btn in self.tabs.items():
            if name == "Browse":
                btn.config(
                    bg='#4a90d9', fg='white', font=('Segoe UI', 10, 'bold')
                )
            else:
                btn.config(bg='#282828', fg='white', font=('Segoe UI', 10))

        for w in self.content_frame.winfo_children():
            w.destroy()
        self.grid.pack(fill='both', expand=True)
        self.render_grid()

    def show_history(self) -> None:
        """Show watch history tab"""
        self.active_tab = "History"
        for name, btn in self.tabs.items():
            btn.config(bg='#282828', fg='white', font=('Segoe UI', 10))
        self.tabs["History"].config(
            bg='#4a90d9', fg='white', font=('Segoe UI', 10, 'bold')
        )

        for w in self.content_frame.winfo_children():
            w.destroy()

        if not self.auth.current_user:
            tk.Label(
                self.content_frame, text="Login to view history",
                font=('Segoe UI', 14), bg='#181818', fg='#888888'
            ).pack(expand=True)
            return

        user_dir = self.auth.get_user_dir(self.auth.current_user)
        history = WatchHistory(user_dir)
        entries = history.get()

        if not entries:
            tk.Label(
                self.content_frame, text="No watch history",
                font=('Segoe UI', 14), bg='#181818', fg='#888888'
            ).pack(expand=True)
            return

        list_frame = tk.Frame(self.content_frame, bg='#181818')
        list_frame.pack(fill='both', expand=True)

        scroll = tk.Frame(list_frame, bg='#282828')
        scroll.pack(fill='both', expand=True)

        lb = tk.Listbox(
            scroll, bg='#1e1e1e', fg='white', font=('Segoe UI', 10),
            selectbackground='#4a90d9'
        )
        lb.pack(side='left', fill='both', expand=True)

        scrollbar = tk.Scrollbar(scroll, orient='vertical', command=lb.yview)
        scrollbar.pack(side='right', fill='y')
        lb.config(yscrollcommand=scrollbar.set)

        for e in entries:
            lb.insert(tk.END, f"{e['title'][:60]}")

        lb.bind(
            '<Double-1>',
            lambda e: self._play_history_item(entries[lb.curselection()[0]])
        )

    def _play_history_item(self, entry: Dict) -> None:
        """Play a video from history"""
        video = {
            'id': entry['video_id'],
            'title': entry['title'],
            'channel': entry['channel']
        }
        self.root.after(0, lambda: self.play_video(video))

    def clear_history(self) -> None:
        """Clear all watch history"""
        if not self.auth.current_user:
            return
        if messagebox.askyesno(
            "Clear History", "Delete all watch history?"
        ):
            user_dir = self.auth.get_user_dir(self.auth.current_user)
            WatchHistory(user_dir).clear()
            self.show_history()

    def show_playlists(self) -> None:
        """Show playlists tab"""
        self.active_tab = "Playlists"
        for name, btn in self.tabs.items():
            btn.config(bg='#282828', fg='white', font=('Segoe UI', 10))
        self.tabs["Playlists"].config(
            bg='#4a90d9', fg='white', font=('Segoe UI', 10, 'bold')
        )

        for w in self.content_frame.winfo_children():
            w.destroy()

        if not self.auth.current_user:
            tk.Label(
                self.content_frame, text="Login to use playlists",
                font=('Segoe UI', 14), bg='#181818', fg='#888888'
            ).pack(expand=True)
            return

        user_dir = self.auth.get_user_dir(self.auth.current_user)
        playlists = Playlists(user_dir)
        names = playlists.list()

        if not names:
            tk.Label(
                self.content_frame, text="No playlists yet",
                font=('Segoe UI', 14), bg='#181818', fg='#888888'
            ).pack(expand=True)

            tk.Label(
                self.content_frame, text="Create your first playlist:",
                font=('Segoe UI', 11), bg='#181818', fg='#888888'
            ).pack(pady=(0, 10))

            create_frame = tk.Frame(self.content_frame, bg='#181818')
            create_frame.pack(fill='x', padx=20)

            name_entry = tk.Entry(
                create_frame, font=('Segoe UI', 11),
                bg='#1e1e1e', fg='white'
            )
            name_entry.pack(fill='x', padx=20, pady=5)

            def do_create() -> None:
                name = name_entry.get().strip()
                if not name:
                    return
                ok, msg = playlists.create(name)
                if ok:
                    self.show_playlists()
                else:
                    messagebox.showerror("Error", msg)

            tk.Button(
                create_frame, text="Create", command=do_create,
                bg='#4caf50', fg='white', font=('Segoe UI', 10, 'bold')
            ).pack(pady=5)
            return

        list_frame = tk.Frame(self.content_frame, bg='#181818')
        list_frame.pack(fill='both', expand=True)

        for i, name in enumerate(names):
            card = tk.Frame(
                list_frame, bg='#282828', relief='flat'
            )
            card.grid(row=i // 2, column=i % 2, padx=12, pady=12, sticky='nsew')

            count = len(playlists.get(name))
            tk.Label(
                card, text=name, font=('Segoe UI', 12, 'bold'),
                bg='#282828', fg='white'
            ).pack(padx=12, pady=8)
            tk.Label(
                card, text=f"{count} video{'s' if count != 1 else ''}",
                font=('Segoe UI', 9), bg='#282828', fg='#888888'
            ).pack(padx=12)

            btn_frame = tk.Frame(card, bg='#282828')
            btn_frame.pack(padx=12, pady=(0, 8))

            tk.Button(
                btn_frame, text="Play",
                command=lambda n=name: self._play_playlist(n),
                bg='#4a90d9', fg='white', font=('Segoe UI', 9),
                relief='flat', width=8
            ).pack(side='left', padx=2)
            tk.Button(
                btn_frame, text="Delete",
                command=lambda n=name: self._delete_playlist(n),
                bg='#f44336', fg='white', font=('Segoe UI', 9),
                relief='flat', width=8
            ).pack(side='left', padx=2)

        for i in range(2):
            list_frame.grid_columnconfigure(i, weight=1)

    def _play_playlist(self, name: str) -> None:
        """Play a playlist in order"""
        user_dir = self.auth.get_user_dir(self.auth.current_user)
        playlists = Playlists(user_dir)
        videos = playlists.get(name)

        if not videos:
            return

        first = videos[0]
        playlist_videos = videos.copy()
        self._current_playlist = name
        self._playlist_index = 0

        original_close = self.close_player

        def close_and_advance() -> None:
            self._playlist_index += 1
            if self._playlist_index < len(playlist_videos):
                self.play_video(playlist_videos[self._playlist_index])
            else:
                self._current_playlist = None
                original_close()

        self.close_player = close_and_advance
        self.play_video(first)

    def _delete_playlist(self, name: str) -> None:
        """Delete a playlist"""
        user_dir = self.auth.get_user_dir(self.auth.current_user)
        playlists = Playlists(user_dir)
        if messagebox.askyesno("Delete", f"Delete '{name}'?"):
            playlists.delete(name)
            self.show_playlists()

    def clear_playlists(self) -> None:
        """Clear all playlists"""
        if not self.auth.current_user:
            return
        if messagebox.askyesno("Clear", "Delete all playlists?"):
            user_dir = self.auth.get_user_dir(self.auth.current_user)
            playlists = Playlists(user_dir)
            for name in playlists.list():
                playlists.delete(name)
            self.show_playlists()

    def set_cookies(self) -> None:
        """Import YouTube cookies file"""
        path = filedialog.askopenfilename(
            title="Select YouTube Cookies",
            filetypes=[("All files", "*.*")]
        )
        if path:
            try:
                import shutil
                shutil.copy(path, COOKIES_FILE)
                if self.auth.current_user:
                    self.auth.users[self.auth.current_user]['yt_authenticated'] = True
                    self.auth.save_users()
                messagebox.showinfo("Saved", "Cookies imported successfully")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def manage_accounts(self) -> None:
        """Show account management dialog"""
        dlg = tk.Toplevel(self.root)
        dlg.title("Accounts")
        dlg.geometry("360x340")
        dlg.configure(bg='#181818')
        dlg.grab_set()

        tk.Label(
            dlg, text="User Accounts",
            font=('Segoe UI', 16, 'bold'),
            bg='#181818', fg='white'
        ).pack(pady=16)

        lb = tk.Listbox(dlg, bg='#1e1e1e', fg='white', height=8)
        lb.pack(fill='both', padx=20, pady=10, expand=True)

        for u in self.auth.users:
            mark = "✓" if self.auth.users[u].get('yt_authenticated') else "○"
            lb.insert(tk.END, f"{mark} {u}")

        def del_user() -> None:
            sel = lb.curselection()
            if sel:
                u = lb.get(sel[0]).split()[-1]
                if messagebox.askyesno("Delete", f"Delete {u}?"):
                    self.auth.delete_user(u)
                    lb.delete(sel[0])

        tk.Button(
            dlg, text="Delete Selected", command=del_user,
            bg='#f44336', fg='white', font=('Segoe UI', 10)
        ).pack(pady=10)

    def show_login(self) -> None:
        """Show login/overlay screen"""
        for w in self.root.winfo_children():
            if w != self.main:
                w.destroy()

        ov = tk.Frame(self.root, bg='#181818')
        ov.place(relx=0, rely=0, relwidth=1, relheight=1)
        ov.pack_propagate(False)

        self.overlay = ov

        lf = tk.Frame(ov, bg='#282828', width=400, height=440)
        lf.pack(expand=True)
        lf.pack_propagate(False)

        tk.Label(
            lf, text="YouTube Stream",
            font=('Segoe UI', 22, 'bold'),
            bg='#282828', fg='white'
        ).pack(pady=40)

        tk.Label(
            lf, text="Username:",
            font=('Segoe UI', 12),
            bg='#282828', fg='white'
        ).pack(pady=(14, 4))
        self.username_entry = tk.Entry(
            lf, font=('Segoe UI', 12),
            bg='#1e1e1e', fg='white'
        )
        self.username_entry.pack(fill='x', padx=40, pady=6)
        self.username_entry.bind(
            '<Return>', lambda e: self.password_entry.focus_set()
        )

        tk.Label(
            lf, text="Password:",
            font=('Segoe UI', 12),
            bg='#282828', fg='white'
        ).pack(pady=(14, 4))
        self.password_entry = tk.Entry(
            lf, font=('Segoe UI', 12),
            bg='#1e1e1e', fg='white', show='•'
        )
        self.password_entry.pack(fill='x', padx=40, pady=6)
        self.password_entry.bind(
            '<Return>', lambda e: self.attempt_login()
        )

        btns = tk.Frame(lf, bg='#282828')
        btns.pack(pady=30)

        tk.Button(
            btns, text="Login", command=self.attempt_login,
            bg='#4a90d9', fg='white', font=('Segoe UI', 11, 'bold'),
            relief='flat'
        ).pack(side='left', padx=(0, 10))

        tk.Button(
            btns, text="Create Account", command=self.create_account,
            bg='#303030', fg='white', font=('Segoe UI', 11),
            relief='flat'
        ).pack(side='left', padx=(0, 0))

        self.username_entry.focus_set()

    def attempt_login(self) -> None:
        """Attempt login with provided credentials"""
        uname = self.username_entry.get()
        pwd = self.password_entry.get()

        if self.auth.authenticate(uname, pwd):
            self.auth.current_user = uname
            self.overlay.destroy()
            self.status.config(text=f"Logged in: {uname}")
        else:
            messagebox.showerror("Error", "Invalid credentials")

    def create_account(self) -> None:
        """Show create account dialog"""
        dlg = tk.Toplevel(self.overlay)
        dlg.title("Create Account")
        dlg.geometry("360x320")
        dlg.configure(bg='#181818')
        dlg.grab_set()

        tk.Label(
            dlg, text="Create Account",
            font=('Segoe UI', 16, 'bold'),
            bg='#181818', fg='white'
        ).pack(pady=16)

        tk.Label(
            dlg, text="Username:",
            font=('Segoe UI', 11),
            bg='#181818', fg='white'
        ).pack(pady=(8, 2))
        user_entry = tk.Entry(dlg, font=('Segoe UI', 11), bg='#1e1e1e', fg='white')
        user_entry.pack(fill='x', padx=30, pady=4)

        tk.Label(
            dlg, text="Password:",
            font=('Segoe UI', 11),
            bg='#181818', fg='white'
        ).pack(pady=(8, 2))
        pass_entry = tk.Entry(
            dlg, show='•', font=('Segoe UI', 11),
            bg='#1e1e1e', fg='white'
        )
        pass_entry.pack(fill='x', padx=30, pady=4)

        def do_create() -> None:
            u = user_entry.get()
            p = pass_entry.get()
            if not u or not p:
                messagebox.showerror("Error", "All fields required")
                return
            ok, msg = self.auth.create_user(u, p)
            if ok:
                messagebox.showinfo("Success", msg)
                dlg.destroy()
            else:
                messagebox.showerror("Error", msg)

        tk.Button(
            dlg, text="Create", command=do_create,
            bg='#4caf50', fg='white', font=('Segoe UI', 11, 'bold')
        ).pack(pady=20, padx=40)

        dlg.bind('<Return>', lambda e: do_create())

    def play_video(self, video: Dict) -> None:
        """Play a video - initialize UI then mpv after idle"""
        video_id = video.get('id')
        title = video.get('title', 'Unknown')
        channel = video.get('channel', 'Unknown')
        url = f'https://www.youtube.com/watch?v={video_id}'

        self.current_video = video
        self.status.config(text=f"Playing: {title[:40]}...")

        for w in self.content_frame.winfo_children():
            w.destroy()

        self._init_player_ui(video)

        self.root.after(50, lambda: self.init_mpv(video))


def main() -> None:
    """Entry point for YouTube Stream app"""
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('clam')
    app = YouTubeStreamApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()