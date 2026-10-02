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
import atexit
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from logsetup import setup_logging
    LOG = setup_logging('youtube_stream.boot')
except Exception:  # logging must never block startup
    import logging
    LOG = logging.getLogger('youtube_stream.boot')

app_dir = Path(__file__).resolve().parent
src_dir = app_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

_server_proc = None


def _cleanup_server() -> None:
    """Kill the Flask child on exit.

    Without this the server was orphaned whenever the GUI exited, leaving a
    stale process holding port 5000 that silently shadowed the next launch.
    """
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        LOG.info('Shutting down Flask server (pid %s)', _server_proc.pid)
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=5)
        except Exception:
            try:
                _server_proc.kill()
            except Exception:
                pass
    _server_proc = None


atexit.register(_cleanup_server)


def _kill_orphan_servers() -> None:
    """Kill leftover stream_server.py processes from earlier runs.

    A stale child that still holds :5000 makes the next launch fail to bind,
    which then surfaces as a confusing 'search timed out' in the UI.
    """
    me = os.getpid()
    try:
        out = subprocess.run(['pgrep', '-f', 'stream_server.py'],
                             capture_output=True, text=True, timeout=5)
    except Exception:
        return
    for pid in out.stdout.split():
        try:
            pid_i = int(pid)
        except ValueError:
            continue
        if pid_i == me:
            continue
        LOG.warning('Killing orphaned Flask server pid=%s', pid_i)
        try:
            os.kill(pid_i, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.5)


def _install_signal_handlers() -> None:
    """Run cleanup on SIGTERM/SIGINT too.

    atexit alone is not enough: SIGKILL cannot be caught, and a SIGTERM would
    otherwise skip cleanup and orphan the Flask child holding port 5000.
    """
    def handler(signum, _frame):
        LOG.info('Received signal %s — shutting down', signum)
        _cleanup_server()
        # Re-raise with the default disposition so the exit code is honest.
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass  # not in the main thread / unsupported


_install_signal_handlers()

# Auto-start the Flask server if not already running
def ensure_server():
    """Check if server is running, start it if not."""
    global _server_proc
    try:
        import urllib.request
        urllib.request.urlopen('http://127.0.0.1:5000/', timeout=2)
        LOG.info('Flask server already listening on :5000 — reusing it')
        return  # server already running
    except Exception as exc:
        LOG.info('No server on :5000 (%s) — starting one', exc)
        # A previous run may have left an orphan holding the port. If nothing
        # answers, it is not actually serving; kill it so the new child binds.
        _kill_orphan_servers()

    # Start server in background
    server_script = src_dir / "stream_server.py"
    _server_proc = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(app_dir),
    )
    LOG.info('Spawned Flask server pid=%s', _server_proc.pid)
    # Wait for server to be ready (up to 10s)
    for _ in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen('http://127.0.0.1:5000/', timeout=2)
            LOG.info('Flask server ready (pid %s)', _server_proc.pid)
            return
        except Exception:
            if _server_proc.poll() is not None:
                LOG.error('Flask server exited early with code %s',
                          _server_proc.returncode)
                return
    LOG.warning('Flask server still not answering after 10s')


if __name__ == "__main__":
    LOG.info('Starting YouTube Stream GUI')
    ensure_server()
    from yt_stream import main
    try:
        main()
    finally:
        LOG.info('GUI exited; cleaning up')
        _cleanup_server()