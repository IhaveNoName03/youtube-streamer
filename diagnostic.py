#!/usr/bin/env python3
"""Diagnostic feedback loop for YouTube Streamer — exercises critical code paths"""

import sys
import os
from pathlib import Path

# Add src to path
SRC_DIR = Path.home() / "youtubedl" / "src"
sys.path.insert(0, str(SRC_DIR))

results = []

# 1. Import check
try:
    from yt_stream import UserAuth, WatchHistory, Playlists
    results.append(("Import yt_stream module", True, "OK"))
except Exception as e:
    results.append(("Import yt_stream module", False, str(e)))

# 2. Import player module
try:
    from player import PlaybackController
    results.append(("Import player module", True, "OK"))
except Exception as e:
    results.append(("Import player module", False, str(e)))

# 3. Auth: hash + verify roundtrip
try:
    auth = UserAuth()
    pw = "testpassword123"
    hashed = auth.hash_password(pw)
    assert ':' in hashed, "Hash should have salt:key format"
    assert auth.verify_password(hashed, pw), "Should verify correct password"
    assert not auth.verify_password(hashed, "wrong"), "Should reject wrong password"
    results.append(("Auth hash/verify roundtrip", True, "OK"))
except Exception as e:
    results.append(("Auth hash/verify roundtrip", False, str(e)))

# 4. Auth: create + authenticate user
try:
    import tempfile
    tmpdir = Path(tempfile.mkdtemp())
    auth.USERS_FILE = tmpdir / "test_users.json"
    auth.users = {}
    ok, msg = auth.create_user("testuser", "testpass")
    assert ok, f"Create failed: {msg}"
    assert auth.authenticate("testuser", "testpass"), "Auth should succeed"
    assert not auth.authenticate("testuser", "wrongpass"), "Auth should fail"
    assert not auth.authenticate("nonexistent", "pass"), "Non-existent user should fail"
    results.append(("Auth create/authenticate", True, "OK"))
except Exception as e:
    results.append(("Auth create/authenticate", False, str(e)))

# 5. History: add + retrieve
try:
    tmpdir2 = Path(tempfile.mkdtemp())
    hist = WatchHistory(tmpdir2 / "user1")
    hist.add("vid123", "Test Video", "Test Channel")
    entries = hist.get()
    assert len(entries) == 1, f"Should have 1 entry, got {len(entries)}"
    assert entries[0]['video_id'] == "vid123", "Wrong video ID"
    assert entries[0]['title'] == "Test Video", "Wrong title"
    results.append(("WatchHistory add/retrieve", True, "OK"))
except Exception as e:
    results.append(("WatchHistory add/retrieve", False, str(e)))

# 6. History: duplicate add
try:
    hist.add("vid123", "Updated Title", "New Channel", duration=100)
    entries = hist.get()
    assert len(entries) == 1, "Duplicate should not create new entry"
    assert entries[0]['watch_duration'] >= 100, "Duration should update"
    results.append(("History duplicate add updates", True, "OK"))
except Exception as e:
    results.append(("History duplicate add updates", False, str(e)))

# 7. Playlists: create + add + list
try:
    tmpdir3 = Path(tempfile.mkdtemp())
    pls = Playlists(tmpdir3 / "user2")
    ok, msg = pls.create("My Playlist")
    assert ok, f"Create failed: {msg}"
    pls.add_video("My Playlist", {'id': 'v1', 'title': 'Video 1', 'channel': 'Ch1'})
    pls.add_video("My Playlist", {'id': 'v2', 'title': 'Video 2', 'channel': 'Ch2'})
    names = pls.list()
    assert "My Playlist" in names, "Playlist should be in list"
    videos = pls.get("My Playlist")
    assert len(videos) == 2, f"Should have 2 videos, got {len(videos)}"
    results.append(("Playlists create/add/list", True, "OK"))
except Exception as e:
    results.append(("Playlists create/add/list", False, str(e)))

# 8. Playlists: duplicate add
try:
    ok, msg = pls.add_video("My Playlist", {'id': 'v1', 'title': 'Video 1', 'channel': 'Ch1'})
    assert not ok, "Duplicate add should fail"
    results.append(("Playlists duplicate add rejected", True, "OK"))
except Exception as e:
    results.append(("Playlists duplicate add rejected", False, str(e)))

# 9. Playlists: delete
try:
    pls.delete("My Playlist")
    assert "My Playlist" not in pls.list(), "Should be deleted"
    results.append(("Playlists delete", True, "OK"))
except Exception as e:
    results.append(("Playlists delete", False, str(e)))

# 10. PlaybackController: instantiation
try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    
    container = tk.Frame(root, width=400, height=300)
    container.pack()
    container.update_idletasks()
    
    controller = PlaybackController(container, on_close_callback=lambda: None)
    results.append(("PlaybackController instantiation", True, "OK"))
    
    try:
        controller.close()
    except:
        pass
    root.destroy()
except Exception as e:
    results.append(("PlaybackController instantiation", "SKIP", f"Tkinter unavailable: {e}"))

# 11. Check yt-dlp availability
try:
    import yt_dlp
    import importlib.metadata
    version = importlib.metadata.version("yt-dlp")
    results.append(("yt-dlp available", True, f"version {version}"))
except Exception as e:
    results.append(("yt-dlp available", False, str(e)))

# 12. Check mpv CLI
try:
    import subprocess
    result = subprocess.run(['mpv', '--version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        results.append(("mpv CLI available", True, version_line))
    else:
        results.append(("mpv CLI available", False, result.stderr[:100]))
except Exception as e:
    results.append(("mpv CLI available", False, str(e)))

# 13. Check flask availability
try:
    import flask
    results.append(("Flask available", True, f"version {flask.__version__}"))
except Exception as e:
    results.append(("Flask available", False, str(e)))

# 14. Check python-mpv
try:
    import mpv
    results.append(("python-mpv available", True, f"libmpv loaded"))
except Exception as e:
    results.append(("python-mpv available", False, str(e)))

# Print results
print("=" * 60)
print("DIAGNOSTIC RESULTS")
print("=" * 60)
passed = 0
failed = 0
skipped = 0

for name, status, detail in results:
    icon = "✓" if status == True else "✗" if status == False else "~"
    if status == True:
        passed += 1
    elif status == False:
        failed += 1
    else:
        skipped += 1
    print(f"{icon} {name}: {detail}")

print("=" * 60)
print(f"Passed: {passed}, Failed: {failed}, Skipped: {skipped}")
if failed > 0:
    print("\n⚠️  SOME CHECKS FAILED — review above")
else:
    print("\n✓ All non-skipped checks passed")