"""FastAPI routes for the local trigger listener."""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.trigger import TriggerCooldown, TriggerForbidden, TriggerService
from app.config import AgentConfig
from app.jobs.manager import JobManager, QueueFullError
from app.time import utc_now


TRIGGER_PATH = "/trigger"


def create_app(
    config: AgentConfig,
    manager: JobManager | None = None,
    *,
    event_clock: Callable | None = None,
) -> FastAPI:
    """Build the trigger-only FastAPI application.

    The request body is intentionally ignored: the network source address is
    the sole routing authority for a physical trigger.
    """

    job_manager = manager or JobManager()
    service = TriggerService(
        config,
        job_manager,
        event_clock=event_clock or utc_now,
    )

    app = FastAPI(title="Hikvision Clip Agent Trigger API")
    app.state.job_manager = job_manager
    app.state.trigger_service = service

    @app.post(TRIGGER_PATH, status_code=202)
    async def trigger(request: Request) -> JSONResponse:
        client = request.client
        source_ip = client.host if client is not None else None
        if not source_ip:
            return JSONResponse(
                status_code=403,
                content={"status": "forbidden", "code": "TRIGGER_FORBIDDEN"},
            )

        try:
            result = service.accept(source_ip)
        except TriggerForbidden:
            return JSONResponse(
                status_code=403,
                content={"status": "forbidden", "code": "TRIGGER_FORBIDDEN"},
            )
        except QueueFullError:
            return JSONResponse(
                status_code=503,
                content={"status": "busy", "code": "QUEUE_FULL"},
            )

        if isinstance(result, TriggerCooldown):
            return JSONResponse(
                status_code=202,
                content={"status": "cooldown", "trigger_id": result.trigger_id},
            )

        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "job_id": result.job.job_id},
        )

    return app
