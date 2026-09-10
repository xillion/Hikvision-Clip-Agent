# Hikvision Clip Agent

Production-oriented Hikvision archive clip worker for ARM64 Linux / Rock Pi 4A.

## Project direction

The implementation follows the supplied `SPEC.md` and is developed incrementally from M0 to M16. Each milestone is completed, tested, and committed separately.

Core pipeline:

`HTTP trigger -> event timestamp -> Hikvision ISAPI search -> playback URI -> one RTSP/FFmpeg stream-copy session -> fragmented MP4 in /dev/shm -> ffprobe validation -> OAuth2 upload -> cleanup`

## Constraints

- Python 3 + FastAPI/Uvicorn.
- Hikvision HTTP ISAPI + RTSP; no HCNetSDK.
- FFmpeg stream copy only; no transcoding.
- One bounded in-memory queue and one worker.
- Temporary video files only under `/dev/shm/hikvision-agent/`.
- No SQLite, Redis, Celery, RabbitMQ, Kafka, MQTT, Docker, or VLC.
- Secrets remain in a dedicated `0600` secrets file and are never logged.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest
python -m compileall app
```

## Milestones

- M0 — repository initialization
- M1 — validated YAML configuration and secrets
- M2 — event timing and cooldown domain logic
- M3 — local trigger API
- M4 — Hikvision archive search
- M5 — playback URI handling
- M6 — FFmpeg extraction
- M7 — ffprobe validation
- M8 — OAuth2 client credentials
- M9 — clip upload
- M10 — end-to-end worker
- M11 — production logging/redaction
- M12 — systemd packaging
- M13 — local Web UI
- M14 — atomic configuration updates
- M15 — production hardening
- M16 — v1.0.0 acceptance/release
