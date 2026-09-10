"""Trigger admission logic: source-IP routing, cooldown, timing, and enqueue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address, ip_network
from typing import Callable
from uuid import uuid4

from app.config import AgentConfig, TriggerConfig
from app.jobs.manager import JobManager, QueueFullError
from app.jobs.models import ClipJob
from app.time import CooldownRegistry, capture_event_timestamp


@dataclass(frozen=True)
class TriggerAccepted:
    job: ClipJob


@dataclass(frozen=True)
class TriggerCooldown:
    trigger_id: str


class TriggerForbidden(PermissionError):
    """Raised when the source address is not a configured trigger."""


class TriggerService:
    """Perform only the fast admission work required by POST /trigger."""

    def __init__(
        self,
        config: AgentConfig,
        manager: JobManager,
        *,
        event_clock: Callable[[], datetime],
        cooldown_registry: CooldownRegistry | None = None,
    ) -> None:
        self._config = config
        self._manager = manager
        self._event_clock = event_clock
        self._cooldowns = cooldown_registry or CooldownRegistry()
        self._triggers = tuple(config.triggers)

    @staticmethod
    def _matches(source_ip: str, address: str) -> bool:
        source = ip_address(source_ip)
        try:
            return source == ip_address(address)
        except ValueError:
            return source in ip_network(address, strict=False)

    def identify(self, source_ip: str) -> TriggerConfig:
        for trigger in self._triggers:
            if self._matches(source_ip, trigger.address):
                return trigger
        raise TriggerForbidden("source address is not a configured trigger")

    def accept(self, source_ip: str) -> TriggerAccepted | TriggerCooldown:
        trigger = self.identify(source_ip)
        if not self._cooldowns.try_accept(trigger.id, trigger.cooldown):
            return TriggerCooldown(trigger_id=trigger.id)

        # Capture the authoritative event timestamp only after source validation
        # and cooldown admission, immediately before enqueueing the job.
        event_timestamp = capture_event_timestamp(self._event_clock)
        job = ClipJob(
            job_id=uuid4().hex,
            trigger_id=trigger.id,
            camera_id=trigger.camera_id,
            event_timestamp=event_timestamp,
        )
        try:
            self._manager.enqueue(job)
        except QueueFullError:
            # Queue capacity must not consume a cooldown slot: a request that was
            # not admitted into the queue did not create a trigger event job.
            self._cooldowns.clear(trigger.id)
            raise
        return TriggerAccepted(job=job)
