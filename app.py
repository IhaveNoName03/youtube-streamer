#!/usr/bin/env python3
"""
YouTube Streaming App - Entry Point
Usage: python app.py
"""

import sys
from pathlib import Path

# Ensure src is in path
app_dir = Path(__file__).parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Import and run main app
from yt_stream import main

if __name__ == "__main__":
    main()