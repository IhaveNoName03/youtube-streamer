#!/usr/bin/env python3
"""Presentation layer: pure functions that turn video dicts into display text.

Kept free of Tk and network so the strings a user actually reads can be
tested directly. yt_stream.render_grid() consumes these instead of formatting
inline, which is what previously made view-count and duration bugs untestable
without spinning up a window.
"""

from typing import Any, Dict, Optional

__all__ = [
    'format_views',
    'format_duration',
    'card_title',
    'card_meta',
    'card_thumbnail',
    'unknown',
]

UNKNOWN = 'Unknown'


def unknown(value: Optional[str]) -> str:
    """Return the value, or a placeholder when it is missing/blank."""
    if value is None:
        return UNKNOWN
    text = str(value).strip()
    return text or UNKNOWN


def format_views(views: Any) -> str:
    """Abbreviate a view count the way YouTube does.

    Accepts whatever the extractor produced: None, a string, or an int. The
    server emits `view_count`; a mismatch here silently renders "0 views" on
    every card, so this is deliberately tolerant of key aliases.
    """
    if views is None or isinstance(views, bool):
        return '0'
    try:
        count = int(views)
    except (TypeError, ValueError):
        return '0'
    if count < 0:
        return '0'
    if count >= 1_000_000:
        return f'{count / 1e6:.1f}M'
    if count >= 1_000:
        return f'{count / 1e3:.1f}K'
    return str(count)


def format_duration(seconds: Any) -> str:
    """Format seconds as H:MM:SS or M:SS. Falsy input yields ''.

    An empty string means "no badge", which is different from "0:00".
    """
    if not seconds:
        return ''
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ''
    if total <= 0:
        return ''
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def card_thumbnail(video: Dict[str, Any]) -> str:
    """Best available thumbnail URL for a video dict."""
    for key in ('thumbnail', 'thumb'):
        url = video.get(key)
        if url:
            return str(url)
    return ''


def card_title(video: Dict[str, Any], max_len: int = 80) -> str:
    """Title plus a duration badge when one is known."""
    title = unknown(video.get('title'))
    if len(title) > max_len:
        title = title[:max_len]
    badge = format_duration(video.get('duration'))
    return f'{title} {badge}' if badge else title


def card_meta(video: Dict[str, Any]) -> str:
    """The 'channel • 1.2M views' line under a card title.

    Reads `view_count` first and falls back to `views` so a server/GUI key
    mismatch degrades to correct text instead of a silent '0 views'.
    """
    channel = unknown(video.get('channel') or video.get('uploader'))
    raw_views = video.get('view_count')
    if raw_views is None:
        raw_views = video.get('views')
    return f'{channel} • {format_views(raw_views)} views'