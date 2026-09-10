"""Tests for trigger routing, cooldown, queue admission, and HTTP contract."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import (
    AgentConfig,
    CameraConfig,
    ClipServerConfig,
    LoggingConfig,
    OAuthConfig,
    RecorderConfig,
    ServerConfig,
    StorageConfig,
    TriggerConfig,
)
from app.jobs.manager import JobManager
from app.jobs.models import ClipJob, JobState


UTC = timezone.utc


def make_config(*, address: str = "10.10.10.10", cooldown: float = 3) -> AgentConfig:
    return AgentConfig(
        id="agent-1",
        mac_address="00:11:22:33:44:55",
        video_duration=30,
        recorders=(RecorderConfig("nvr-1", "http://nvr.local", "admin"),),
        cameras=(CameraConfig("camera-1", "nvr-1", 101),),
        triggers=(TriggerConfig("button-1", "camera-1", address, cooldown),),
        clip_server=ClipServerConfig(
            "http://clip.local",
            OAuthConfig("http://clip.local/o/token/", "http://clip.local/api/upload-clip/"),
        ),
        trigger_server=ServerConfig("0.0.0.0", 8090),
        web_server=ServerConfig("0.0.0.0", 8080),
        storage=StorageConfig("/dev/shm/hikvision-agent"),
        logging=LoggingConfig("/var/log/hikvision-agent/agent.log"),
    )


def test_trigger_is_routed_by_source_ip_and_client_body_is_ignored() -> None:
    manager = JobManager(maxsize=2)
    event = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    app = create_app(make_config(), manager, event_clock=lambda: event)

    with TestClient(app, client=("10.10.10.10", 40000)) as client:
        response = client.post("/trigger", json={"camera_id": "attacker-selected-camera"})

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    job = manager.queue.get_nowait()
    assert job.job_id == response.json()["job_id"]
    assert job.trigger_id == "button-1"
    assert job.camera_id == "camera-1"
    assert job.event_timestamp == event
    assert job.state == JobState.QUEUED


def test_unknown_source_is_forbidden_and_creates_no_job() -> None:
    manager = JobManager(maxsize=2)
    app = create_app(make_config(), manager)

    with TestClient(app, client=("10.10.10.11", 40000)) as client:
        response = client.post("/trigger", json={"camera_id": "camera-1"})

    assert response.status_code == 403
    assert response.json() == {"status": "forbidden", "code": "TRIGGER_FORBIDDEN"}
    assert manager.qsize() == 0


def test_cidr_source_matches_trigger() -> None:
    manager = JobManager(maxsize=2)
    event = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    app = create_app(make_config(address="10.10.10.0/24"), manager, event_clock=lambda: event)

    with TestClient(app, client=("10.10.10.42", 40000)) as client:
        response = client.post("/trigger")

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_second_event_during_cooldown_returns_202_without_job() -> None:
    manager = JobManager(maxsize=2)
    event = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    app = create_app(make_config(cooldown=30), manager, event_clock=lambda: event)

    with TestClient(app, client=("10.10.10.10", 40000)) as client:
        first = client.post("/trigger")
        second = client.post("/trigger")

    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert second.status_code == 202
    assert second.json() == {"status": "cooldown", "trigger_id": "button-1"}
    assert manager.qsize() == 1


def test_queue_full_returns_busy_and_does_not_consume_cooldown() -> None:
    manager = JobManager(maxsize=1)
    event = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    manager.enqueue(ClipJob("existing", "other", "camera-1", event))
    app = create_app(make_config(cooldown=30), manager, event_clock=lambda: event)

    with TestClient(app, client=("10.10.10.10", 40000)) as client:
        busy = client.post("/trigger")
        manager.queue.get_nowait()
        accepted = client.post("/trigger")

    assert busy.status_code == 503
    assert busy.json() == {"status": "busy", "code": "QUEUE_FULL"}
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"
