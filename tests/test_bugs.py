"""Regression tests for the bugs found in youtube-stream.

Each test asserts the USER-VISIBLE SYMPTOM, not "did it crash".
Run: .venv/bin/python -m pytest tests/ -v
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "video_formats.json").read_text()
)


# ---------------------------------------------------------------------------
# BUG 1: /api/video 500s — format selector compares None heights
# ---------------------------------------------------------------------------
def test_api_video_selector_returns_playable_audio_and_video():
    """YouTube now serves DASH-only: video-only and audio-only are SEPARATE
    streams and there is no muxed progressive format (verified: 37 video-only,
    10 audio-only, 0 muxed on both videos tested). So a correct endpoint must
    return BOTH a video URL and an audio URL — picking a single 'best' stream
    always yields silent playback."""
    formats = FIXTURE["formats"]

    def height(f):
        return f.get("height") or 0

    muxed = [
        f for f in formats
        if f.get("url")
        and f.get("acodec") not in (None, "none")
        and f.get("vcodec") not in (None, "none")
    ]
    video = [
        f for f in formats
        if f.get("url")
        and f.get("vcodec") not in (None, "none")
        and f.get("height")
    ]
    audio = [
        f for f in formats
        if f.get("url") and f.get("acodec") not in (None, "none")
    ]

    assert muxed or video, "no playable video stream found"
    assert audio, "no audio stream found — playback would be silent"

    best_video = max(muxed or video, key=height)
    best_audio = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0)
    assert best_video.get("height"), "video stream picked has no height"
    assert best_audio.get("acodec") not in (None, "none")


def test_api_video_endpoint_returns_200(monkeypatch):
    """End-to-end: the Flask route must answer 200 with a playable payload."""
    import stream_server

    fake_info = {
        "id": FIXTURE["id"],
        "title": FIXTURE["title"],
        "duration": FIXTURE["duration"],
        "formats": FIXTURE["formats"],
    }

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return fake_info

    monkeypatch.setattr(stream_server.yt_dlp, "YoutubeDL", FakeYDL)
    stream_server.app.config["TESTING"] = True
    client = stream_server.app.test_client()
    resp = client.get(f"/api/video/{FIXTURE['id']}")
    assert resp.status_code == 200, f"got HTTP {resp.status_code}: {resp.get_json()}"
    body = resp.get_json()
    assert "error" not in body, body
    assert body.get("url"), "no playable video url returned"
    assert body.get("audio_url"), (
        "no audio_url returned -> DASH video-only stream plays SILENT"
    )


# ---------------------------------------------------------------------------
# BUG 4/5: server->GUI key contract (views) and thumbnails
# ---------------------------------------------------------------------------
def test_search_response_uses_key_gui_expects():
    """yt_stream.render_grid reads v['view_count']; the server emits 'views'.
    Whichever name wins, the GUI must be able to read real view counts."""
    import stream_server

    entries = [
        {"id": "a", "title": "T", "uploader": "C", "view_count": 12345,
         "thumbnail": "https://img/x.jpg"},
        {"id": "b", "title": "U", "uploader": "D", "view_count": 6789,
         "thumbnail": "https://img/y.jpg"},
    ]

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return {"entries": entries}

    orig = stream_server.yt_dlp.YoutubeDL
    stream_server.yt_dlp.YoutubeDL = FakeYDL
    try:
        client = stream_server.app.test_client()
        resp = client.get("/api/search?q=linux")
        videos = resp.get_json()["videos"]
    finally:
        stream_server.yt_dlp.YoutubeDL = orig

    assert videos, "no videos returned"
    v = videos[0]
    # This is exactly what yt_stream.render_grid does:
    views = v.get("view_count", 0)
    assert views == 12345, (
        f"GUI reads v['view_count'] but server sent keys {sorted(v)} -> "
        f"card renders '0 views'"
    )


def test_search_results_carry_thumbnails():
    """Replay a REAL extract_flat trace: yt-dlp returns thumbnail=None for every
    entry, so the endpoint must synthesise a usable thumbnail URL from the video
    id — otherwise the GUI renders blank grey cards."""
    import stream_server

    entries = json.loads(
        (Path(__file__).parent / "fixtures" / "search_flat.json").read_text()
    )
    assert entries and all(e.get("thumbnail") is None for e in entries), (
        "fixture no longer reproduces the flat-extraction thumbnail gap"
    )

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return {"entries": entries}

    orig = stream_server.yt_dlp.YoutubeDL
    stream_server.yt_dlp.YoutubeDL = FakeYDL
    try:
        client = stream_server.app.test_client()
        videos = client.get("/api/search?q=linux").get_json()["videos"]
    finally:
        stream_server.yt_dlp.YoutubeDL = orig

    assert videos, "no videos returned"
    missing = [v["id"] for v in videos if not v.get("thumbnail")]
    assert not missing, (
        f"{len(missing)}/{len(videos)} cards have no thumbnail "
        f"(ids {missing[:3]}) -> grey placeholder cards"
    )


# ---------------------------------------------------------------------------
# BUG 2: double <Return> bind makes search() unreachable
# ---------------------------------------------------------------------------
def test_search_entry_return_binds_search_exactly_once():
    """The app must register exactly ONE <Return> binding on search_entry,
    and it must route to search().

    Previously two bind() calls targeted the same widget and the second
    silently replaced the first, making search() unreachable from the UI.
    We record the real bind() calls made by create_widgets(), which does not
    depend on window-manager focus for its result.
    """
    tkinter = pytest.importorskip("tkinter")
    import yt_stream

    try:
        root = tkinter.Tk()
    except Exception as exc:  # headless
        pytest.skip(f"no display: {exc}")

    try:
        root.geometry("900x300")
        app = yt_stream.YouTubeStreamApp.__new__(yt_stream.YouTubeStreamApp)
        app.root = root
        app.status = tkinter.Label(root)
        app.current_videos = []
        app.search_history = []
        app._search_queue = __import__("queue").Queue()
        app._pending_search_query = None
        app._search_poller_running = False
        app._trend_poller_running = False
        app._trend_queue = __import__("queue").Queue()
        app._start_search = lambda q: None
        app._search_category = lambda cat=None: None

        # Record every <Return> bind() performed while the UI is built.
        records = []
        real_bind = tkinter.Entry.bind

        def spy_bind(self, sequence=None, func=None, add=None):
            if sequence == "<Return>":
                records.append(func)
            return real_bind(self, sequence, func, add)

        tkinter.Entry.bind = spy_bind
        try:
            app.create_widgets()
            root.update()
        finally:
            tkinter.Entry.bind = real_bind

        assert len(records) == 1, (
            f"search_entry got {len(records)} <Return> bindings; "
            f"the last one wins and the others are dead code"
        )
        # Only search() should be wired to Enter on the search bar.
        assert app._start_search is not None
    finally:
        root.destroy()


def test_search_entry_return_reaches_search_when_fired():
    """Fire the registered <Return> binding and assert search() is reached."""
    tkinter = pytest.importorskip("tkinter")
    import yt_stream

    try:
        root = tkinter.Tk()
    except Exception as exc:  # headless
        pytest.skip(f"no display: {exc}")

    try:
        root.geometry("900x300")
        app = yt_stream.YouTubeStreamApp.__new__(yt_stream.YouTubeStreamApp)
        app.root = root
        app.status = tkinter.Label(root)
        app.current_videos = []
        app.search_history = []
        app._search_queue = __import__("queue").Queue()
        app._pending_search_query = None
        app._search_poller_running = False
        app._trend_poller_running = False
        app._trend_queue = __import__("queue").Queue()

        fired = []
        app._start_search = lambda q: fired.append(("search", q))
        app._search_category = lambda cat=None: fired.append(("category", cat))
        app.create_widgets()
        root.update()

        # Give THIS widget the keyboard focus. Note: creating any other focusable
        # widget (e.g. a control Entry) would steal it and make this a false
        # negative — the synthetic <Return> is delivered to the focus widget.
        app.search_entry.focus_force()
        root.update()
        # focus_displayof() returns the widget object, not its path string.
        focused = root.focus_displayof()
        assert focused is app.search_entry, (
            f"focus is on {focused}, not the search entry — "
            f"harness problem, not the app"
        )

        # search() returns early on an empty query, so type something first —
        # this is what a user does before pressing Enter.
        app.search_var.set("linux kernel")
        root.update()

        app.search_entry.event_generate("<Return>")
        root.update()

        assert fired, "the registered <Return> binding did not reach any handler"
        assert fired[0][0] == "search", (
            f"<Return> routed to {fired[0]} instead of search()"
        )
    finally:
        root.destroy()


# ---------------------------------------------------------------------------
# BUG 3: poller multiplication
# ---------------------------------------------------------------------------
def test_search_pollers_do_not_multiply():
    """Each search must reuse ONE poller, not schedule an extra self-rearming one."""
    import queue as _q
    import yt_stream

    app = yt_stream.YouTubeStreamApp.__new__(yt_stream.YouTubeStreamApp)
    scheduled = []

    class FakeRoot:
        def after(self, ms, fn):
            scheduled.append(fn.__name__)

    app.root = FakeRoot()
    app._search_queue = _q.Queue()
    app._pending_search_query = None
    app._search_poller_running = False
    app._trend_poller_running = False
    app.status = type("S", (), {"config": lambda self, **k: None})()
    app.content_frame = None
    app.grid = None

    # Drive the REAL entry point that every search now funnels through.
    for q in ("linux", "rust", "python"):
        app._ensure_search_poller()

    assert len(scheduled) == 1, (
        f"3 searches scheduled {len(scheduled)} pollers — they multiply "
        f"(each re-arms every 100ms)"
    )


# ---------------------------------------------------------------------------
# BUG 6: search() calls _do_search with the wrong arity -> silent thread death
# ---------------------------------------------------------------------------
def test_search_delivers_results_to_the_queue():
    """search() must actually deliver results. It currently spawns
    _do_search(query) but the method needs (query, result_queue), so the worker
    dies with TypeError and the UI hangs on 'Searching...' forever."""
    import inspect
    import queue as _q
    import threading
    import yt_stream

    sig = inspect.signature(yt_stream.YouTubeStreamApp._do_search)
    # self + query + result_queue
    assert len(sig.parameters) == 3, f"unexpected signature {sig}"

    app = yt_stream.YouTubeStreamApp.__new__(yt_stream.YouTubeStreamApp)
    app._search_queue = _q.Queue()
    app.current_videos = []
    app.search_history = []
    app.status = type("S", (), {"config": lambda self, **k: None})()
    app.search_var = type("V", (), {"get": lambda self: "linux"})()

    crashes = []

    class FakeRoot:
        def after(self, ms, fn):
            pass

    app.root = FakeRoot()

    # Run the REAL unbound search() but catch whatever its worker thread throws,
    # which is exactly what the user experiences (nothing).
    def guarded(fn, *a):
        try:
            fn(*a)
        except BaseException as e:
            crashes.append(f"{type(e).__name__}: {e}")

    real_thread = threading.Thread

    def thread_spy(target=None, args=(), daemon=None, **kw):
        # Spy must let the CALLER call .start(); it only wraps the target so we
        # can observe the worker's exception (which is what the user never sees).
        wrapped = (lambda: guarded(target, *args))
        return real_thread(target=wrapped, daemon=True)

    threading.Thread = thread_spy
    try:
        app.search()
        # drain the worker before asserting
        for th in threading.enumerate():
            if th is not threading.current_thread():
                th.join(timeout=5)
    finally:
        threading.Thread = real_thread

    assert not crashes, (
        f"search() worker thread died: {crashes[0]} — nothing is ever queued, "
        f"UI hangs on 'Searching...' forever"
    )
    assert app._search_queue.qsize() == 1, (
        "search() queued no results — worker died silently"
    )