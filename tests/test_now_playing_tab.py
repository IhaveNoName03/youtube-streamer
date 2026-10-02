"""Tests for the 'Now Playing' tab.

Before this, playback evicted the whole content area: play_video destroyed the
grid and built the player directly in content_frame, so there was no way to get
back to browsing without stopping the video. The player now lives in a
persistent player_frame that no other view destroys.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

import yt_stream  # noqa: E402
from yt_stream import YouTubeStreamApp  # noqa: E402


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except Exception as exc:  # headless
        pytest.skip(f"no display: {exc}")
    root.geometry("1000x700")
    style = ttk.Style()
    style.theme_use("clam")
    a = YouTubeStreamApp(root)
    end = time.time() + 0.6
    while time.time() < end:
        root.update()
        time.sleep(0.02)
    a._pump = lambda s=0.3: [root.update() or time.sleep(0.02)
                             for _ in range(int(s / 0.02))]
    yield a
    root.destroy()


VIDEO = {"id": "abc123", "title": "Test Video", "channel": "Chan",
         "view_count": 1234, "duration": 100, "thumbnail": ""}


def test_now_playing_tab_is_registered(app):
    assert "Now Playing" in app.tabs, f"tabs={list(app.tabs)}"


def test_now_playing_tab_starts_disabled(app):
    """Disabled until something is actually playing."""
    assert str(app.tabs["Now Playing"].cget("state")) == "disabled"


def test_player_frame_is_separate_from_grid(app):
    """The player needs its own container or it evicts the grid."""
    assert hasattr(app, "player_frame")
    assert app.player_frame is not app.grid


def test_player_survives_switching_tabs(app):
    """The core requirement: playback is not evicted by navigation."""
    app.current_video = VIDEO
    app._init_player_ui(VIDEO)
    app._pump()
    assert app.player_canvas.winfo_exists() == 1

    for view in (app.show_browse, app.show_history, app.show_playlists):
        view()
        app._pump()
        assert app.player_canvas.winfo_exists() == 1, (
            f"{view.__name__} destroyed the player — playback must survive "
            f"tab switches"
        )


def test_grid_survives_player_tab(app):
    app.current_videos = [VIDEO]
    app.show_browse()
    app._pump()
    app.current_video = VIDEO
    app._init_player_ui(VIDEO)
    app.show_now_playing()
    app._pump()
    assert app.grid.winfo_exists() == 1, "grid was destroyed by the player tab"


def test_now_playing_shows_the_player(app):
    app.current_video = VIDEO
    app._init_player_ui(VIDEO)
    app.show_now_playing()
    app._pump()
    assert app.active_tab == "Now Playing"
    assert app.player_canvas.winfo_manager() == "pack"


def test_now_playing_empty_state(app):
    """With nothing playing the tab shows a placeholder, not a crash."""
    app.current_video = None
    app.show_now_playing()
    app._pump()
    labels = [w.cget("text") for w in app.player_frame.winfo_children()
              if isinstance(w, tk.Label)]
    assert any("Nothing playing" in str(t) for t in labels), labels


def test_close_player_disables_tab_and_returns_to_browse(app):
    app.current_video = VIDEO
    app._init_player_ui(VIDEO)
    app._set_tab_enabled("Now Playing", True)
    app.close_player()
    app._pump()
    assert str(app.tabs["Now Playing"].cget("state")) == "disabled"
    assert app.active_tab == "Browse"


def test_highlight_moves_between_tabs(app):
    """Exactly one tab carries the accent colour at a time."""
    accent = yt_stream.ACCENT
    app.show_browse()
    app._pump()
    assert app.tabs["Browse"].cget("bg") == accent

    app.show_history()
    app._pump()
    assert app.tabs["History"].cget("bg") == accent, \
        "History did not become the highlighted tab"
    assert app.tabs["Browse"].cget("bg") != accent, \
        "Browse stayed highlighted after switching away"

    app.show_playlists()
    app._pump()
    assert app.tabs["Playlists"].cget("bg") == accent
    assert app.tabs["History"].cget("bg") != accent, \
        "two tabs highlighted at once"