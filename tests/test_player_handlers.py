"""Tests for the app's mpv event/control handlers.

Observed crash: with python-mpv 1.x, property observers fire once with None
before the file is parsed, and the handle itself is None until load() succeeds.
The handlers compared `None > 0` and raised TypeError on every tick:

    TypeError: '>' not supported between instances of 'NoneType' and 'int'

MpvHandle logs handler exceptions rather than letting them kill mpv, so these
fired silently until logging was added.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yt_stream  # noqa: E402


def _app(player_attr):
    """A YouTubeStreamApp with only the attributes these handlers touch."""
    app = yt_stream.YouTubeStreamApp.__new__(yt_stream.YouTubeStreamApp)
    app.player = player_attr
    calls = []
    app.seek_var = types.SimpleNamespace(set=lambda v: calls.append(("seek_var", v)))
    app.time_lbl = types.SimpleNamespace(config=lambda **k: calls.append(("time_lbl", k)))
    app.play_btn = types.SimpleNamespace(config=lambda **k: calls.append(("play_btn", k)))
    return app, calls


class FakeHandle:
    """Stands in for the mpv handle; every field settable per test."""
    def __init__(self, **kw):
        self.duration = None
        self.playback_time = None
        self.pause = False
        self.volume = 100
        self.playback_rate = 1.0
        self.fullscreen = False
        self.seek = None
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# _update_time / _update_duration / _update_play_state
# ---------------------------------------------------------------------------
def test_update_time_tolerates_none_value():
    app, calls = _app(types.SimpleNamespace(player=FakeHandle(duration=10)))
    app._update_time(None, None)          # the observed crash
    assert calls == [], f"handler acted on a None value: {calls}"


def test_update_time_tolerates_none_duration():
    app, calls = _app(types.SimpleNamespace(player=FakeHandle(duration=None)))
    app._update_time(None, 5.0)           # duration not parsed yet
    assert calls == [], f"handler acted on a None duration: {calls}"


def test_update_time_updates_when_both_present():
    app, calls = _app(types.SimpleNamespace(player=FakeHandle(duration=200)))
    app._update_time(None, 50.0)
    assert calls, "a valid time update did nothing"
    kinds = {c[0] for c in calls}
    assert "seek_var" in kinds and "time_lbl" in kinds


def test_update_time_survives_missing_player():
    app, calls = _app(None)
    app._update_time(None, 5.0)          # player torn down mid-playback
    assert calls == []


def test_update_duration_tolerates_none():
    app, calls = _app(None)
    app._update_duration(None, None)      # the observed crash
    assert calls == [], f"handler acted on a None duration: {calls}"


def test_update_duration_updates_when_known():
    app, calls = _app(None)
    app._update_duration(None, 125)
    assert calls and calls[0][0] == "time_lbl"


def test_update_play_state_tolerates_none():
    app, calls = _app(None)
    app._update_play_state(None, None)
    assert calls == []


# ---------------------------------------------------------------------------
# control callbacks
# ---------------------------------------------------------------------------
def test_mpv_helper_returns_none_when_absent():
    app, _ = _app(None)
    assert app._mpv() is None
    app2, _ = _app(types.SimpleNamespace(player=None))
    assert app2._mpv() is None, "controller with no handle must yield None"


@pytest.mark.parametrize("call,args", [
    ("_on_seek_drag", ("50",)),
    ("_on_volume_change", ("80",)),
    ("_on_speed_change", ("1.5x",)),
    ("toggle_play_pause", ()),
    ("toggle_fullscreen", ()),
    ("seek", (5.0,)),
])
def test_controls_are_safe_with_no_player(call, args):
    """Every control must be a no-op, not a crash, before playback starts."""
    app, _ = _app(None)
    getattr(app, call)(*args)             # must not raise


@pytest.mark.parametrize("call,args", [
    ("_on_seek_drag", ("50",)),
    ("_on_volume_change", ("80",)),
    ("_on_speed_change", ("1.5x",)),
    ("toggle_play_pause", ()),
    ("toggle_fullscreen", ()),
    ("seek", (5.0,)),
])
def test_controls_are_safe_when_duration_is_none(call, args):
    """Handle exists but duration is not known yet — still must not raise."""
    app, _ = _app(types.SimpleNamespace(player=FakeHandle(duration=None)))
    getattr(app, call)(*args)


def test_controls_actually_drive_the_handle():
    app, _ = _app(types.SimpleNamespace(player=FakeHandle(duration=200)))
    # The sliders are 0-100 and the handlers scale to mpv's 0-100 volume
    # convention being expressed as a 0-1 fraction (see _on_volume_change).
    app._on_volume_change("80")
    assert app._mpv().volume == pytest.approx(0.8)

    app._on_speed_change("1.5x")
    assert app._mpv().playback_rate == pytest.approx(1.5)

    app.toggle_play_pause()
    assert app._mpv().pause is True

    # seek bar is a percentage of duration (200s) -> 50% = 100s
    app._on_seek_drag("50")
    assert app._mpv().seek == pytest.approx(100.0)