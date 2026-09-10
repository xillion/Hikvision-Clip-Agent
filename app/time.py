"""Event timing and per-trigger cooldown domain logic."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable


class TimeError(ValueError):
    """Raised when an event timestamp cannot be used safely."""


@dataclass(frozen=True)
class ClipInterval:
    """The archive interval requested for a trigger event."""

    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def utc_now() -> datetime:
    """Return the current timezone-aware UTC wall-clock time."""

    return datetime.now(timezone.utc)


def capture_event_timestamp(clock: Callable[[], datetime] = utc_now) -> datetime:
    """Capture the event time at the caller boundary and normalize it to UTC."""

    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeError("event timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def build_clip_interval(event_timestamp: datetime, duration_seconds: float) -> ClipInterval:
    """Build [event_timestamp - duration, event_timestamp]."""

    if event_timestamp.tzinfo is None or event_timestamp.utcoffset() is None:
        raise TimeError("event timestamp must be timezone-aware")
    if duration_seconds <= 0:
        raise TimeError("video duration must be > 0")
    end = event_timestamp.astimezone(timezone.utc)
    start = end - timedelta(seconds=duration_seconds)
    return ClipInterval(start=start, end=end)


class CooldownRegistry:
    """In-memory per-trigger cooldown using a monotonic clock.

    Monotonic time is deliberately used for cooldowns so NTP/wall-clock
    adjustments cannot unexpectedly extend or bypass a cooldown.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_accepted: dict[str, float] = {}

    def try_accept(self, trigger_id: str, cooldown_seconds: float) -> bool:
        if not trigger_id:
            raise ValueError("trigger_id must not be empty")
        if cooldown_seconds < 0:
            raise ValueError("cooldown must be >= 0")

        now = self._clock()
        last = self._last_accepted.get(trigger_id)
        if last is not None and now - last < cooldown_seconds:
            return False
        self._last_accepted[trigger_id] = now
        return True

    def clear(self, trigger_id: str) -> None:
        self._last_accepted.pop(trigger_id, None)

    def clear_all(self) -> None:
        self._last_accepted.clear()
