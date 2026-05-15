"""Tests for domain.text_utils.

These pin the *current* behavior of ``humanize_age`` (extracted from the three
duplicated ``_humanize`` helpers in dashboard/deck_detail/deck_card). Any
intentional behavior change goes in a separate follow-up.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from anki_git_ui.domain.text_utils import humanize_age


NOW = datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc)


def _earlier(seconds: int) -> datetime:
    return NOW - timedelta(seconds=seconds)


def test_returns_default_fallback_when_dt_is_none() -> None:
    assert humanize_age(None, now=NOW) == "never"


def test_respects_custom_fallback() -> None:
    assert humanize_age(None, fallback="–", now=NOW) == "–"


@pytest.mark.parametrize(
    "seconds_ago, expected",
    [
        # < 60s → "just now"
        (0, "just now"),
        (1, "just now"),
        (59, "just now"),
        # 60s exactly → "1 minute ago" (singular at 60-119s)
        (60, "1 minute ago"),
        (119, "1 minute ago"),
        # >= 120s → plural "minutes"
        (120, "2 minutes ago"),
        (3599, "59 minutes ago"),
        # 3600s exactly → "1 hour ago" (singular at 3600-7199s)
        (3600, "1 hour ago"),
        (7199, "1 hour ago"),
        # >= 7200s → plural "hours"
        (7200, "2 hours ago"),
        (86399, "23 hours ago"),
        # 86400s exactly → "1 day ago" (singular at exactly 1 day)
        (86400, "1 day ago"),
        # > 1 day → plural "days"
        (86400 * 2, "2 days ago"),
        (86400 * 30, "30 days ago"),
    ],
)
def test_pinned_boundaries(seconds_ago: int, expected: str) -> None:
    assert humanize_age(_earlier(seconds_ago), now=NOW) == expected


def test_naive_datetime_treated_as_utc() -> None:
    # Mirrors the original `_humanize` behavior: tz-naive dt is interpreted
    # as UTC rather than the local zone.
    naive = datetime(2026, 5, 11, 0, 0, 0)  # 24h before NOW
    assert humanize_age(naive, now=NOW) == "1 day ago"


def test_default_now_uses_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``now`` is omitted, ``datetime.now(timezone.utc)`` is consulted."""
    frozen = datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr("anki_git_ui.domain.text_utils.datetime", _Frozen)
    assert humanize_age(_earlier(60)) == "1 minute ago"
