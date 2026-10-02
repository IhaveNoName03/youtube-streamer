"""Tests for the logging setup (src/logsetup.py).

The bug these guard: app.py calls setup_logging('youtube_stream.boot') at import
time, and yt_stream later calls setup_logging(). The second call used to no-op,
so the auth/search loggers never got handlers and their output was silently
discarded — the exact failure that hid the login trail.
"""
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(code: str) -> str:
    """Run a snippet in a fresh interpreter so logging state is isolated."""
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(ROOT),
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin",
             "HOME": "/tmp", "YT_LOG_DIR": "/tmp"},
        timeout=60,
    )
    return (r.stdout or "") + (r.stderr or "")


def test_child_first_call_still_configures_root():
    """setup_logging('some.child') first must configure the ROOT handlers."""
    out = _run(
        "import sys; sys.path.insert(0, 'src')\n"
        "from logsetup import setup_logging, get_logger\n"
        "setup_logging('youtube_stream.boot')   # app.py does this first\n"
        "setup_logging()                       # yt_stream does this next\n"
        "a = get_logger('auth')\n"
        "a.info('AUTHLINE_MARKER')\n"
        "b = get_logger('search')\n"
        "b.info('SEARCHLINE_MARKER')\n"
    )
    assert "AUTHLINE_MARKER" in out, (
        "auth logger produced no output — a child-first setup_logging() call "
        f"left the root unconfigured. Got: {out[:300]}"
    )
    assert "SEARCHLINE_MARKER" in out, (
        f"search logger produced no output. Got: {out[:300]}"
    )


def test_every_module_logger_reaches_the_file():
    """auth, search, server and boot logs must all land in the log file."""
    logfile = "/tmp/pytest_logsetup_check.log"
    Path(logfile).unlink(missing_ok=True)
    out = _run(
        "import sys; sys.path.insert(0, 'src')\n"
        "from logsetup import setup_logging, get_logger\n"
        "setup_logging('youtube_stream.boot')\n"
        "for n in ('boot', 'auth', 'search', 'server.request', 'player', 'ui'):\n"
        "    get_logger(n).info('MARK_' + n.replace('.', '_'))\n"
    )
    text = Path(logfile).read_text() if Path(logfile).exists() else out
    for marker in ("MARK_boot", "MARK_auth", "MARK_search",
                   "MARK_server_request", "MARK_player", "MARK_ui"):
        assert marker in text, f"{marker} never reached the log. Output: {out[:300]}"
    Path(logfile).unlink(missing_ok=True)


def test_passwords_are_never_logged():
    """Auth logging must not include the password value."""
    out = _run(
        "import sys; sys.path.insert(0, 'src')\n"
        "from logsetup import setup_logging\n"
        "setup_logging('youtube_stream.boot')\n"
        "import yt_stream, tempfile, pathlib\n"
        "p = pathlib.Path(tempfile.mkdtemp()) / 'users.json'\n"
        "yt_stream.USERS_FILE = p\n"
        "a = yt_stream.UserAuth()\n"
        "a.create_user('bob', 'SUPERSECRET123')\n"
        "a.authenticate('bob', 'SUPERSECRET123')\n"
        "a.authenticate('bob', 'WRONGPASS999')\n"
    )
    assert "SUPERSECRET123" not in out, "the real password was written to the log"
    assert "WRONGPASS999" not in out, "the attempted password was written to the log"
    # ...but the outcome must still be recorded.
    assert "login OK" in out, f"successful login was not logged. Got: {out[:400]}"
    assert "login FAILED" in out, f"failed login was not logged. Got: {out[:400]}"


def test_worker_thread_failure_is_logged():
    """A dying worker thread must leave a traceback in the log.

    This is the original silent-hang class of bug: _do_search ran in a daemon
    thread, so an exception vanished and the UI waited forever.
    """
    out = _run(
        "import sys; sys.path.insert(0, 'src')\n"
        "from logsetup import setup_logging\n"
        "setup_logging()\n"
        "import yt_stream, threading\n"
        "def boom():\n"
        "    try:\n"
        "        yt_stream.log_search.info('about to fail')\n"
        "        raise ValueError('worker exploded')\n"
        "    except Exception:\n"
        "        yt_stream.log_search.exception('search FAILED')\n"
        "t = threading.Thread(target=boom); t.start(); t.join()\n"
    )
    assert "search FAILED" in out, f"failure not logged. Got: {out[:300]}"
    assert "ValueError" in out, "no traceback recorded — the point is the traceback"
    assert "about to fail" in out