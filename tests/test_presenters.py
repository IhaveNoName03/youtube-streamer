"""Tests for the pure presentation layer (src/presenters.py).

These are the strings a user actually reads. Before this module existed the
formatting was inline in render_grid(), so a view-count or duration regression
could only be caught by opening a window and reading pixels — which is why the
'0 views' bug survived so long.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from presenters import (  # noqa: E402
    card_meta,
    card_thumbnail,
    card_title,
    format_duration,
    format_views,
)


# ---------------------------------------------------------------------------
# view counts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    (0, "0"),
    (999, "999"),
    (1_000, "1.0K"),
    (1_500, "1.5K"),
    (999_999, "1000.0K"),
    (1_000_000, "1.0M"),
    (2_833_731, "2.8M"),
    (999_999_999, "1000.0M"),
    (None, "0"),
    ("", "0"),
    ("not-a-number", "0"),
    (-5, "0"),
])
def test_format_views(raw, expected):
    assert format_views(raw) == expected


def test_card_meta_uses_view_count_not_views():
    """The regression: server emitted 'views', GUI read 'view_count'.

    card_meta must prefer view_count and fall back to views so a key mismatch
    degrades to correct text rather than silently reading 0.
    """
    v = {"channel": "Chan", "view_count": 2_833_731}
    assert card_meta(v) == "Chan • 2.8M views"


def test_card_meta_falls_back_to_views_key():
    v = {"channel": "Chan", "views": 1_500}
    assert card_meta(v) == "Chan • 1.5K views"


def test_card_meta_never_reports_zero_when_data_present():
    """Regression guard for the original bug: real counts must never show as 0."""
    for key in ("view_count", "views"):
        v = {"channel": "C", key: 930_631}
        assert "0 views" not in card_meta(v), (
            f"a real view count rendered as '0 views' via key {key!r}"
        )


def test_card_meta_handles_missing_fields():
    assert card_meta({}) == "Unknown • 0 views"
    assert card_meta({"channel": "  "}) == "Unknown • 0 views"


# ---------------------------------------------------------------------------
# durations
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    (0, ""),            # no badge
    (None, ""),
    ("", ""),
    ("bad", ""),
    (-10, ""),
    (5, "0:05"),
    (59, "0:59"),
    (60, "1:00"),
    (605, "10:05"),
    (3600, "1:00:00"),
    (3661, "1:01:01"),
    (86399, "23:59:59"),
])
def test_format_duration(raw, expected):
    assert format_duration(raw) == expected


def test_card_title_appends_duration_badge():
    v = {"title": "Test Video", "duration": 125}
    assert card_title(v) == "Test Video 2:05"


def test_card_title_without_duration_has_no_badge():
    v = {"title": "Test Video"}
    assert card_title(v) == "Test Video"
    assert not card_title(v).endswith(" ")


def test_card_title_truncates_long_titles():
    v = {"title": "x" * 200}
    out = card_title(v)
    assert len(out) == 80, f"expected 80 chars, got {len(out)}"
    assert out == "x" * 80


def test_card_title_missing_title():
    assert card_title({}) == "Unknown"


def test_card_title_truncation_keeps_badge_visible():
    v = {"title": "y" * 200, "duration": 65}
    out = card_title(v, max_len=20)
    assert out.startswith("y" * 20)
    assert "1:05" in out


# ---------------------------------------------------------------------------
# thumbnails
# ---------------------------------------------------------------------------
def test_card_thumbnail_prefers_thumbnail_key():
    v = {"thumbnail": "https://i.ytimg.com/vi/x/hqdefault.jpg"}
    assert card_thumbnail(v) == "https://i.ytimg.com/vi/x/hqdefault.jpg"


def test_card_thumbnail_empty_when_absent():
    assert card_thumbnail({}) == ""
    assert card_thumbnail({"thumbnail": None}) == ""
    assert card_thumbnail({"thumbnail": ""}) == ""


# ---------------------------------------------------------------------------
# full-card rendering, as the grid would show it
# ---------------------------------------------------------------------------
def test_card_renders_real_search_payload():
    """A payload shaped like the real /api/search response."""
    v = {
        "id": "JDfo2Lc7iLU",
        "title": "The Linux Kernel: What it is, and how it works",
        "channel": "The Linux Experiment",
        "view_count": 260_880,
        "duration": 754,
        "thumbnail": "https://i.ytimg.com/vi/JDfo2Lc7iLU/hqdefault.jpg",
    }
    assert card_title(v) == "The Linux Kernel: What it is, and how it works 12:34"
    assert card_meta(v) == "The Linux Experiment • 260.9K views"
    assert card_thumbnail(v).endswith("hqdefault.jpg")
    assert "0 views" not in card_meta(v)


def test_presentation_never_raises_on_junk():
    """Garbage from the extractor must not crash grid rendering."""
    for v in (None, {}, {"title": None, "view_count": "abc"},
              {"duration": object()}, {"channel": 12345}):
        if v is None:
            continue
        card_title(v)
        card_meta(v)
        card_thumbnail(v)