"""Bounded single-consumer job queue."""

from __future__ import annotations

import asyncio

from app.jobs.models import ClipJob


DEFAULT_QUEUE_SIZE = 8


class QueueFullError(RuntimeError):
    """Raised when the trigger queue has no free slot."""


class JobManager:
    """Own the one bounded queue used by the worker pipeline."""

    def __init__(self, maxsize: int = DEFAULT_QUEUE_SIZE) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        self.queue: asyncio.Queue[ClipJob] = asyncio.Queue(maxsize=maxsize)

    def enqueue(self, job: ClipJob) -> None:
        """Enqueue without waiting; the HTTP handler must never block on capacity."""

        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            raise QueueFullError("job queue is full") from exc

    def qsize(self) -> int:
        return self.queue.qsize()

    def full(self) -> bool:
        return self.queue.full()
