"""Domain models for Hikvision archive search results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SearchSegment:
    track_id: int
    start: datetime
    end: datetime
    playback_uri: str
    codec_type: str


class HikvisionError(RuntimeError):
    """Base class for Hikvision integration failures."""


class HikvisionAuthError(HikvisionError):
    """Recorder authentication failed."""


class HikvisionHttpError(HikvisionError):
    """Recorder returned an unexpected HTTP response."""


class HikvisionXmlError(HikvisionError):
    """Recorder returned malformed or unusable XML."""


class HikvisionNoRecording(HikvisionError):
    """No archive segment contains the requested start time."""
