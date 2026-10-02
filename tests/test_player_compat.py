"""Tests for the python-mpv 1.x compatibility layer (src/player.py:MpvHandle).

The app's player code was written against python-mpv 0.x, where
``MPV.bind(name, callback)`` existed. 1.0 removed it, which produced the
runtime error 'mpv property does not exist ... b"bind"' and meant playback
never started. MpvHandle restores that surface.

These run against a real mpv handle; they skip if no display is available.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

pytest.importorskip("mpv")
tk = pytest.importorskip("tkinter")

from player import MpvHandle  # noqa: E402


@pytest.fixture(scope="module")
def handle():
    try:
        root = tk.Tk()
    except Exception as exc:  # headless
        pytest.skip(f"no display: {exc}")
    root.geometry("320x240")
    frame = tk.Frame(root, bg="black")
    frame.pack(fill="both", expand=True)
    root.update()
    h = MpvHandle(wid=str(frame.winfo_id()), keep_open=False,
                  pause=False, force_window=True)
    yield h, root
    try:
        h.quit()
    except Exception:
        pass
    root.destroy()


def test_bind_method_exists(handle):
    """0.x bind() must exist again — its absence was the whole bug.

    Note: we must CALL it. mpv.MPV defines __getattr__, so hasattr()/getattr()
    return something for any name; only invocation raises. Checking the
    attribute's presence passes even on the broken raw handle.
    """
    h, root = handle
    seen = []
    h.bind("pause", lambda event, value: seen.append(event))
    for _ in range(20):
        root.update(); time.sleep(0.05)
    assert seen, (
        "bind() did not deliver — a raw mpv.MPV handle raises "
        "'mpv property does not exist' here instead"
    )


def test_property_subscription_fires(handle):
    """A property handler must be invoked with the 0.x (event, value) shape."""
    h, root = handle
    seen = []
    h.bind("pause", lambda event, value: seen.append((event, value)))
    for _ in range(20):
        root.update(); time.sleep(0.05)
    assert seen, "observe_property handler never fired for 'pause'"
    name, _value = seen[0]
    assert name == "pause", f"handler got event name {name!r}, expected 'pause'"


def test_event_subscription_is_registered_not_crashing(handle):
    """Subscribing to an EVENT name must not raise (0.x style call)."""
    h, _ = handle
    got = []
    h.bind("idle", lambda event, value: got.append(event))
    assert callable(h._dispatch_event)
    # feed a synthetic event through the dispatcher
    h._dispatch_event("idle", True)
    assert got == ["idle"], f"event dispatcher did not route 'idle': {got}"


def test_handler_exception_does_not_propagate(handle):
    """A raising handler must be logged, not crash the mpv callback."""
    h, root = handle
    h.bind("volume", lambda event, value: 1 / 0)
    for _ in range(10):   # if it propagated, mpv would blow up here
        root.update(); time.sleep(0.03)


def test_attribute_delegation_still_works(handle):
    """Property get/set must pass through to the real handle."""
    h, _ = handle
    h.volume = 33
    assert float(h.volume) == 33, f"volume delegation broken: {h.volume}"
    h.pause = True
    assert h.pause is True
    h.pause = False


def test_controller_load_uses_the_compat_handle(tmp_path):
    """PlaybackController.load() must construct MpvHandle, not raw mpv.MPV.

    This is the path the app actually takes. Testing MpvHandle in isolation
    would pass even if the controller went back to the broken raw handle, so
    this asserts on the constructor the controller really calls.
    """
    import ast
    import inspect
    import textwrap
    import player

    src = textwrap.dedent(inspect.getsource(player.PlaybackController.load))
    tree = ast.parse(src)
    constructed = {
        getattr(n.func, "id", None) or getattr(n.func, "attr", None)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
        in ("MpvHandle", "MPV")
    }
    assert "MpvHandle" in constructed, (
        f"PlaybackController.load builds {constructed or 'nothing'} — a raw "
        f"mpv.MPV has no bind(), so playback dies with "
        f"'mpv property does not exist'"
    )
    assert "MPV" not in constructed, (
        "controller still constructs raw mpv.MPV somewhere"
    )


def test_audio_track_is_attached_with_audio_add():
    """DASH audio must be attached with audio_add(), not loadfile append.

    Observed: loadfile(video,'replace') + loadfile(audio,'append') plays the
    video SILENTLY — `append` queues a second file rather than attaching the
    audio track. audio_add() is what produces an audio codec.
    """
    import ast
    import inspect
    import textwrap
    import player

    src = textwrap.dedent(inspect.getsource(player.PlaybackController.load))
    tree = ast.parse(src)

    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    assert "audio_add" in calls, (
        "load() never calls audio_add() — appending the audio URL with "
        "'loadfile ... append' plays video with no sound"
    )
    # the broken pattern must be gone
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "command":
                for a in node.args:
                    if isinstance(a, ast.Constant) and a.value == "loadfile":
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Constant) and \
                                    sub.value == "append":
                                raise AssertionError(
                                    "loadfile(...,'append') is still used for the "
                                    "audio stream; it does not attach audio"
                                )


def test_no_idle_option_is_passed():
    """idle=False kills the libmpv core; it must never be passed again."""
    import ast
    import inspect
    import textwrap
    import player

    src = textwrap.dedent(inspect.getsource(player.PlaybackController.load))
    tree = ast.parse(src)

    # Find every MPVHandle(...)/MPV(...) call and check its keywords. Matching
    # on the raw text would false-positive on the explanatory comment.
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in ("MpvHandle", "MPV"):
                for kw in node.keywords:
                    if kw.arg == "idle":
                        offenders.append(kw.arg)

    assert not offenders, (
        f"idle= passed to mpv constructor — it shuts the core down and every "
        f"later call raises 'libmpv core has been shutdown': {offenders}"
    )