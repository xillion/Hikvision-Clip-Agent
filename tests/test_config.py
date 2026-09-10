"""M1 configuration validation tests."""

from pathlib import Path

import pytest

from app.config import ConfigError, load_config, load_secrets


VALID_CONFIG = """
id: hikvision-agent
device:
  mac_address: "00:11:22:33:44:55"
video:
  duration: 30
recorders:
  - id: nvr-1
    url: "http://192.168.1.10"
    username: admin
cameras:
  - id: camera-1
    recorder_id: nvr-1
    track_id: 101
triggers:
  - id: button-1
    camera_id: camera-1
    address: "192.168.1.20"
    cooldown: 3
clip_server:
  url: "https://clips.example.test"
trigger_server:
  host: "0.0.0.0"
  port: 8090
web_server:
  host: "127.0.0.1"
  port: 8080
storage:
  temp_dir: "/dev/shm/hikvision-agent"
logging:
  path: "/var/log/hikvision-agent/agent.log"
"""

VALID_SECRETS = """
recorders:
  nvr-1:
    password: secret
clip_server:
  oauth:
    client_id: client
    client_secret: secret
"""


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))
    assert config.video_duration == 30
    assert config.cameras[0].track_id == 101
    assert config.clip_server.oauth.token_url.endswith("/o/token/")


def test_load_valid_secrets(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))
    secrets = load_secrets(write(tmp_path, "secrets.yaml", VALID_SECRETS), config)
    assert secrets.recorders["nvr-1"].password == "secret"


@pytest.mark.parametrize(
    "replacement, message",
    [
        ("  duration: 0", "duration"),
        ("    track_id: 0", "track_id"),
        ("    cooldown: -1", "cooldown"),
        ('    address: "not-an-ip"', "address"),
        ('    recorder_id: missing', "recorder_id"),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, replacement: str, message: str) -> None:
    content = VALID_CONFIG
    if replacement.startswith("  ") and replacement.strip().startswith("duration"):
        content = content.replace("  duration: 30", replacement)
    elif replacement.strip().startswith("track_id"):
        content = content.replace("    track_id: 101", replacement)
    elif replacement.strip().startswith("cooldown"):
        content = content.replace("    cooldown: 3", replacement)
    elif replacement.strip().startswith("address"):
        content = content.replace('    address: "192.168.1.20"', replacement)
    else:
        content = content.replace("    recorder_id: nvr-1", replacement)
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, "config.yaml", content))


def test_missing_recorder_secret_is_rejected(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))
    secrets = VALID_SECRETS.replace("  nvr-1:\n    password: secret\n", "")
    with pytest.raises(ConfigError, match="nvr-1"):
        load_secrets(write(tmp_path, "secrets.yaml", secrets), config)


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(write(tmp_path, "config.yaml", "id: ["))
