#!/usr/bin/env python3
"""
YouTube Streaming App - Clean YouTube-like streaming experience
Self-contained installation with local user auth and YouTube cookie support
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
import webbrowser
import io

# Try to import dependencies
try:
    import requests
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests', '-q'], check=True, stdout=subprocess.DEVNULL)
    import requests

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ============================================================================
# CONFIGURATION - Self-contained paths
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

# API endpoint
SERVER_URL = "http://127.0.0.1:5000"

# Create directories
for d in [DATA_DIR, DATA_DIR / "cookies", DOWNLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================================
# USER AUTHENTICATION
# ============================================================================

class UserAuth:
    def __init__(self):
        self.users = {}
        self.current_user = None
        self.load_users()
    
    def load_users(self):
        if USERS_FILE.exists():
            try:
                with open(USERS_FILE, 'r') as f:
                    self.users = json.load(f)
            except:
                self.users = {}
    
    def save_users(self):
        with open(USERS_FILE, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def hash_password(self, password):
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return salt.hex() + ':' + key.hex()
    
    def verify_password(self, stored, provided):
        salt, key = stored.split(':')
        new_key = hashlib.pbkdf2_hmac('sha256', provided.encode(), bytes.fromhex(salt), 100000)
        return new_key.hex() == key
    
    def create_user(self, username, password):
        if username in self.users:
            return False, "Username already exists"
        self.users[username] = {'password': self.hash_password(password),
                                'created': datetime.now().isoformat(),
                                'yt_authenticated': False}
        self.save_users()
        return True, "User created successfully"
    
    def authenticate(self, username, password):
        if username not in self.users:
            return False
        return self.verify_password(self.users[username]['password'], password)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class YouTubeStreamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Stream")
        self.root.geometry("1400x900")
        self.root.configure(bg='#181818')
        
        self.auth = UserAuth()
        self.current_videos = []
        self.server = None
        
        self.create_widgets()
        self.start_server()
        self.show_login_screen()
    
    def create_widgets(self):
        self.main = tk.Frame(self.root, bg='#181818')
        self.main.pack(fill='both', expand=True, padx=24, pady=24)
        
        # Header
        header = tk.Frame(self.main, bg='#090909', height=56)
        header.pack(fill='x')
        tk.Label(header, text="🎬 YouTube Stream", font=('Segoe UI', 18, 'bold'),
                bg='#090909', fg='white').pack(pady=14)
        
        # Search
        search = tk.Frame(self.main, bg='#181818')
        search.pack(fill='x', pady=(0, 24))
        
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(search, textvariable=self.search_var,
                                    font=('Segoe UI', 14), bg='#282828', fg='white',
                                    insertbackground='white', relief='flat')
        self.search_entry.pack(side='left', fill='x', expand=True, padx=(0, 12))
        self.search_entry.bind('<Return>', lambda e: self.search())
        
        tk.Button(search, text="Search", command=self.search,
                 bg='#4a90d9', fg='white', font=('Segoe UI', 12, 'bold'),
                 relief='flat').pack(side='right')
        
        # Video grid
        self.grid = tk.Frame(self.main, bg='#181818')
        self.grid.pack(fill='both', expand=True)
        
        # Status
        self.status = tk.Label(self.main, text="Ready", font=('Segoe UI', 10),
                              bg='#181818', fg='#888888')
        self.status.pack(side='bottom', anchor='w', padx=24, pady=(24, 0))
        
        # Menu
        self.create_menu()
    
    def create_menu(self):
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
        tools.add_command(label="Open Config", command=lambda: webbrowser.open(f'file://{DATA_DIR}'))
    
    def start_server(self):
        def run():
            try:
                subprocess.Popen([sys.executable, str(SERVER_SCRIPT)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass
        
        threading.Thread(target=run, daemon=True).start()
        self.check_server()
    
    def check_server(self):
        try:
            requests.get(SERVER_URL, timeout=2)
            self.status.config(text="Connected")
        except:
            self.status.config(text="Connecting...")
            self.root.after(500, self.check_server)
    
    def search(self):
        query = self.search_var.get().strip()
        if not query:
            return
        
        self.current_videos = []
        self.status.config(text=f"Searching: {query}...")
        
        def do_search():
            try:
                resp = requests.get(f'{SERVER_URL}/api/search',
                                    params={'q': query}, timeout=10)
                data = resp.json()
                videos = data.get('videos', [])
                
                def update():
                    self.current_videos = videos
                    self.render_grid()
                    self.status.config(text=f"Found {len(videos)} videos")
                
                self.root.after(0, update)
            except Exception as e:
                self.status.config(text=f"Error: {e}")
        
        threading.Thread(target=do_search, daemon=True).start()
    
    def render_grid(self):
        for w in self.grid.winfo_children():
            w.destroy()
        
        if not self.current_videos:
            self.grid.config(text="No videos found")
            tk.Label(self.grid, text="No videos found", fg='#888888',
                    bg='#181818', font=('Segoe UI', 14)).pack(expand=True)
            return
        
        for i, v in enumerate(self.current_videos):
            r, c = i // 4, i % 4
            
            card = tk.Frame(self.grid, bg='#282828', relief='flat', cursor='hand2')
            card.grid(row=r, column=c, padx=12, pady=12, sticky='nsew')
            
            # Thumbnail
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
                except:
                    pass
            
            # Title
            tk.Label(card, text=v.get('title', 'Unknown')[:80],
                    font=('Segoe UI', 10), bg='#282828', fg='white',
                    wraplength=300).pack(padx=12, pady=6)
            
            # Meta
            views = v.get('view_count', 0)
            vs = f"{views/1e6:.1f}M" if views >= 1e6 else f"{views/1e3:.1f}K" if views >= 1e3 else str(views)
            tk.Label(card, text=f"{v.get('channel', 'Unknown')} • {vs} views",
                    font=('Segoe UI', 9), bg='#282828', fg='#888888').pack(padx=12, pady=(0, 12))
            
            card.bind('<Button-1>', lambda e, vid=v: self.play_video(vid))
        
        for i in range(4):
            self.grid.grid_columnconfigure(i, weight=1)
    
    def play_video(self, video):
        self.status.config(text=f"Playing: {video.get('title', '')[:40]}...")
        webbrowser.open(f'{SERVER_URL}/proxy/{video.get("id")}')
    
    def set_cookies(self):
        path = filedialog.askopenfilename(title="Select YouTube Cookies",
                                         filetypes=[("All files", "*.*")])
        if path:
            try:
                import shutil
                dest = COOKIES_FILE
                shutil.copy(path, dest)
                if self.auth.current_user:
                    self.auth.users[self.auth.current_user]['yt_authenticated'] = True
                    self.auth.save_users()
                messagebox.showinfo("Saved", "Cookies imported successfully")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def manage_accounts(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Accounts")
        dlg.geometry("360x340")
        dlg.configure(bg='#181818')
        dlg.grab_set()
        
        tk.Label(dlg, text="User Accounts", font=('Segoe UI', 16, 'bold'),
                bg='#181818', fg='white').pack(pady=16)
        
        lb = tk.Listbox(dlg, bg='#1e1e1e', fg='white', height=8)
        lb.pack(fill='both', padx=20, pady=10, expand=True)
        
        for u in self.auth.users:
            mark = "✓" if self.auth.users[u].get('yt_authenticated') else "○"
            lb.insert(tk.END, f"{mark} {u}")
        
        def del_user():
            sel = lb.curselection()
            if sel:
                u = lb.get(sel[0]).split()[-1]
                if messagebox.askyesno("Delete", f"Delete {u}?"):
                    del self.auth.users[u]
                    self.auth.save_users()
                    lb.delete(sel[0])
        
        tk.Button(dlg, text="Delete Selected", command=del_user,
                 bg='#f44336', fg='white', font=('Segoe UI', 10)).pack(pady=10)
    
    def show_login(self):
        ov = tk.Frame(self.root, bg='#181818')
        ov.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        lf = tk.Frame(ov, bg='#282828', width=400, height=450)
        lf.pack(expand=True)
        lf.pack_propagate(False)
        
        tk.Label(lf, text="YouTube Stream", font=('Segoe UI', 22, 'bold'),
                bg='#282828', fg='white').pack(pady=44)
        
        user_e = tk.Entry(lf, font=('Segoe UI', 12), bg='#1e1e1e', fg='white')
        for lbl in ['Username:', 'Password:']:
            tk.Label(lf, text=lbl, font=('Segoe UI', 12), bg='#282828', fg='white').pack(pady=(14,6))
            e = tk.Entry(lf, font=('Segoe UI', 12), bg='#1e1e1e', fg='white',
                        show='•' if 'Password' in lbl else '')
            e.pack(fill='x', padx=36, pady=6)
            e.bind('<Return>', lambda ev: None)
            if lbl == 'Username:':
                user_e = e
        
        def login():
            uname = user_e.get()
            pwd = lf.winfo_children()[5].get()  # password entry
            if self.auth.authenticate(uname, pwd):
                self.auth.current_user = uname
                ov.destroy()
                self.status.config(text=f"Logged in: {uname}")
            else:
                messagebox.showerror("Error", "Invalid credentials")
        
        def create():
            dlg2 = tk.Toplevel(lf)
            dlg2.title("Create Account")
            dlg2.configure(bg='#181818')
            
            tk.Label(dlg2, text="Username:", bg='#181818', fg='white', font=('Segoe UI',11)).pack(pady=8)
            u = tk.Entry(dlg2, font=('Segoe UI',11), bg='#1e1e1e', fg='white')
            u.pack(fill='x', padx=30, pady=4)
            
            tk.Label(dlg2, text="Password:", bg='#181818', fg='white', font=('Segoe UI',11)).pack(pady=8)
            p = tk.Entry(dlg2, show='•', font=('Segoe UI',11), bg='#1e1e1e', fg='white')
            p.pack(fill='x', padx=30, pady=4)
            
            def do_create():
                if not u.get() or not p.get():
                    return
                ok, msg = self.auth.create_user(u.get(), p.get())
                messagebox.showinfo("Result", msg) if ok else messagebox.showerror("Error", msg)
                if ok:
                    dlg2.destroy()
            
            tk.Button(dlg2, text="Create", command=do_create,
                     bg='#4caf50', fg='white', font=('Segoe UI',11,'bold')).pack(pady=20)
        
        btns = tk.Frame(lf, bg='#282828')
        btns.pack(pady=28)
        tk.Button(btns, text="Login", command=login, bg='#4a90d9', fg='white',
                 font=('Segoe UI',11,'bold'), width=10).pack(side='left', padx=10)
        tk.Button(btns, text="Create", command=create, bg='#303030', fg='white',
                 font=('Segoe UI',11), width=10).pack(side='left', padx=10)
    
    def show_login(self):
        self.show_login(self)

import io

def main():
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('clam')
    app = YouTubeStreamApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()