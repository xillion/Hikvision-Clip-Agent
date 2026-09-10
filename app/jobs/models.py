"""Runtime job models for the bounded in-memory queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ClipJob:
    """Minimal runtime job accepted by the trigger API."""

    job_id: str
    trigger_id: str
    camera_id: str
    event_timestamp: datetime
    state: JobState = JobState.QUEUED
