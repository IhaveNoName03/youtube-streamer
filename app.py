#!/usr/bin/env python3
"""
YouTube Streaming App - Entry Point
Starts the Flask proxy server + Tkinter GUI
Usage: python app.py
"""

import sys
import subprocess
import time
import os
from pathlib import Path

# Ensure src is in path
app_dir = Path(__file__).parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Auto-start the Flask server if not already running
def ensure_server():
    """Check if server is running, start it if not."""
    try:
        import urllib.request
        urllib.request.urlopen('http://127.0.0.1:5000/', timeout=2)
        return  # server already running
    except Exception:
        pass

    # Start server in background
    server_script = src_dir / "stream_server.py"
    proc = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(app_dir),
    )
    # Wait for server to be ready (up to 10s)
    for _ in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen('http://127.0.0.1:5000/', timeout=2)
            print("Server started (PID {})".format(proc.pid), file=sys.stderr)
            return
        except Exception:
            if proc.poll() is not None:
                print("Server failed to start", file=sys.stderr)
                return
    print("Server may still be starting...", file=sys.stderr)


if __name__ == "__main__":
    ensure_server()
    from yt_stream import main
    main()