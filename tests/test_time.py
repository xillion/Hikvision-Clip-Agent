"""Tests for event timing, clip intervals, and cooldowns."""

from datetime import datetime, timedelta, timezone

import pytest

from app.time import CooldownRegistry, TimeError, build_clip_interval, capture_event_timestamp


UTC = timezone.utc


def test_event_timestamp_is_captured_and_normalized_to_utc() -> None:
    instant = datetime(2026, 9, 11, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=2)))
    assert capture_event_timestamp(lambda: instant) == datetime(2026, 9, 11, 10, 34, 56, 123456, tzinfo=UTC)


def test_naive_event_timestamp_is_rejected() -> None:
    with pytest.raises(TimeError, match="timezone-aware"):
        capture_event_timestamp(lambda: datetime(2026, 9, 11, 12, 0))


def test_clip_interval_uses_event_time_as_end() -> None:
    event = datetime(2026, 9, 11, 12, 0, 30, tzinfo=UTC)
    interval = build_clip_interval(event, 30)
    assert interval.end == event
    assert interval.start == datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    assert interval.duration == timedelta(seconds=30)


def test_fractional_duration_is_preserved() -> None:
    event = datetime(2026, 9, 11, 12, 0, 30, tzinfo=UTC)
    interval = build_clip_interval(event, 2.5)
    assert interval.start == event - timedelta(seconds=2.5)


def test_non_positive_duration_is_rejected() -> None:
    event = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    with pytest.raises(TimeError, match="duration"):
        build_clip_interval(event, 0)


def test_cooldown_is_per_trigger() -> None:
    now = [100.0]
    registry = CooldownRegistry(lambda: now[0])
    assert registry.try_accept("button-a", 3) is True
    assert registry.try_accept("button-b", 3) is True
    assert registry.try_accept("button-a", 3) is False


def test_cooldown_expires_at_boundary() -> None:
    now = [100.0]
    registry = CooldownRegistry(lambda: now[0])
    assert registry.try_accept("button", 3) is True
    now[0] = 103.0
    assert registry.try_accept("button", 3) is True


def test_zero_cooldown_accepts_every_event() -> None:
    now = [100.0]
    registry = CooldownRegistry(lambda: now[0])
    assert registry.try_accept("button", 0) is True
    assert registry.try_accept("button", 0) is True


def test_cooldown_uses_monotonic_clock_even_if_wall_clock_is_unavailable() -> None:
    now = [10.0]
    registry = CooldownRegistry(lambda: now[0])
    assert registry.try_accept("button", 5) is True
    now[0] = 12.0
    assert registry.try_accept("button", 5) is False
    now[0] = 15.0
    assert registry.try_accept("button", 5) is True


def test_clear_allows_immediate_reaccept() -> None:
    registry = CooldownRegistry(lambda: 10.0)
    assert registry.try_accept("button", 30) is True
    registry.clear("button")
    assert registry.try_accept("button", 30) is True


def test_invalid_cooldown_is_rejected() -> None:
    registry = CooldownRegistry(lambda: 10.0)
    with pytest.raises(ValueError, match="cooldown"):
        registry.try_accept("button", -1)
