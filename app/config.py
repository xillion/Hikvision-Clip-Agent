"""Validated YAML configuration loading for the agent."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


class ConfigError(ValueError):
    """Raised when runtime configuration or secrets are invalid."""


@dataclass(frozen=True)
class RecorderConfig:
    id: str
    url: str
    username: str


@dataclass(frozen=True)
class CameraConfig:
    id: str
    recorder_id: str
    track_id: int


@dataclass(frozen=True)
class TriggerConfig:
    id: str
    camera_id: str
    address: str
    cooldown: float


@dataclass(frozen=True)
class OAuthConfig:
    token_url: str
    upload_url: str


@dataclass(frozen=True)
class ClipServerConfig:
    url: str
    oauth: OAuthConfig


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class StorageConfig:
    temp_dir: str


@dataclass(frozen=True)
class LoggingConfig:
    path: str


@dataclass(frozen=True)
class AgentConfig:
    id: str
    mac_address: str
    video_duration: float
    recorders: tuple[RecorderConfig, ...]
    cameras: tuple[CameraConfig, ...]
    triggers: tuple[TriggerConfig, ...]
    clip_server: ClipServerConfig
    trigger_server: ServerConfig
    web_server: ServerConfig
    storage: StorageConfig
    logging: LoggingConfig


@dataclass(frozen=True)
class RecorderSecret:
    password: str


@dataclass(frozen=True)
class SecretsConfig:
    recorders: dict[str, RecorderSecret]
    client_id: str
    client_secret: str


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be a mapping")
    return value


def _required(mapping: dict[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"missing {path}.{key}")
    return mapping[key]


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ConfigError(f"{path} must be a non-empty string")
    return value.strip()


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ConfigError(f"{path} must be >= {minimum}")
    return result


def _port(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError(f"{path} must be an integer in 1..65535")
    return value


def _url(value: Any, path: str, *, schemes: tuple[str, ...] = ("http", "https")) -> str:
    result = _string(value, path)
    parsed = urlparse(result)
    if parsed.scheme not in schemes or not parsed.netloc:
        raise ConfigError(f"{path} must be a valid URL with scheme {schemes}")
    return result.rstrip("/")


def _mac(value: Any, path: str) -> str:
    result = _string(value, path).lower()
    parts = result.split(":")
    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        raise ConfigError(f"{path} must be a MAC address")
    try:
        bytes.fromhex("".join(parts))
    except ValueError as exc:
        raise ConfigError(f"{path} must be a MAC address") from exc
    return result


def _address(value: Any, path: str) -> str:
    result = _string(value, path)
    try:
        ip_address(result)
    except ValueError:
        try:
            ip_network(result, strict=False)
        except ValueError as exc:
            raise ConfigError(f"{path} must be an IP address or CIDR") from exc
    return result


def _unique_ids(items: list[Any], path: str) -> None:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"{path} contains duplicate ids")


def load_yaml(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} root must be a mapping")
    return data


def load_config(path: str | Path) -> AgentConfig:
    root = load_yaml(path)
    device = _mapping(_required(root, "device", "config"), "config.device")
    video = _mapping(_required(root, "video", "config"), "config.video")
    recorder_values = _required(root, "recorders", "config")
    camera_values = _required(root, "cameras", "config")
    trigger_values = _required(root, "triggers", "config")
    if not isinstance(recorder_values, list) or not isinstance(camera_values, list) or not isinstance(trigger_values, list):
        raise ConfigError("config.recorders/cameras/triggers must be lists")

    recorders: list[RecorderConfig] = []
    for index, raw in enumerate(recorder_values):
        item = _mapping(raw, f"config.recorders[{index}]")
        recorders.append(RecorderConfig(
            _string(_required(item, "id", f"config.recorders[{index}]"), f"config.recorders[{index}].id"),
            _url(_required(item, "url", f"config.recorders[{index}]"), f"config.recorders[{index}].url"),
            _string(_required(item, "username", f"config.recorders[{index}]"), f"config.recorders[{index}].username"),
        ))

    cameras: list[CameraConfig] = []
    for index, raw in enumerate(camera_values):
        item = _mapping(raw, f"config.cameras[{index}]")
        track_id = _required(item, "track_id", f"config.cameras[{index}]")
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id <= 0:
            raise ConfigError(f"config.cameras[{index}].track_id must be a positive integer")
        cameras.append(CameraConfig(
            _string(_required(item, "id", f"config.cameras[{index}]"), f"config.cameras[{index}].id"),
            _string(_required(item, "recorder_id", f"config.cameras[{index}]"), f"config.cameras[{index}].recorder_id"),
            track_id,
        ))

    triggers: list[TriggerConfig] = []
    for index, raw in enumerate(trigger_values):
        item = _mapping(raw, f"config.triggers[{index}]")
        triggers.append(TriggerConfig(
            _string(_required(item, "id", f"config.triggers[{index}]"), f"config.triggers[{index}].id"),
            _string(_required(item, "camera_id", f"config.triggers[{index}]"), f"config.triggers[{index}].camera_id"),
            _address(_required(item, "address", f"config.triggers[{index}]"), f"config.triggers[{index}].address"),
            _number(_required(item, "cooldown", f"config.triggers[{index}]"), f"config.triggers[{index}].cooldown", minimum=0),
        ))

    _unique_ids(recorders, "config.recorders")
    _unique_ids(cameras, "config.cameras")
    _unique_ids(triggers, "config.triggers")
    recorder_ids = {item.id for item in recorders}
    camera_ids = {item.id for item in cameras}
    if any(item.recorder_id not in recorder_ids for item in cameras):
        raise ConfigError("config.cameras references an unknown recorder_id")
    if any(item.camera_id not in camera_ids for item in triggers):
        raise ConfigError("config.triggers references an unknown camera_id")

    clip_server = _mapping(_required(root, "clip_server", "config"), "config.clip_server")
    trigger_server = _mapping(_required(root, "trigger_server", "config"), "config.trigger_server")
    web_server = _mapping(_required(root, "web_server", "config"), "config.web_server")
    storage = _mapping(_required(root, "storage", "config"), "config.storage")
    logging = _mapping(_required(root, "logging", "config"), "config.logging")

    clip_url = _url(_required(clip_server, "url", "config.clip_server"), "config.clip_server.url")
    return AgentConfig(
        id=_string(_required(root, "id", "config"), "config.id"),
        mac_address=_mac(_required(device, "mac_address", "config.device"), "config.device.mac_address"),
        video_duration=_number(_required(video, "duration", "config.video"), "config.video.duration", minimum=0.001),
        recorders=tuple(recorders), cameras=tuple(cameras), triggers=tuple(triggers),
        clip_server=ClipServerConfig(clip_url, OAuthConfig(
            f"{clip_url}/o/token/", f"{clip_url}/api/upload-clip/")),
        trigger_server=ServerConfig(
            _string(_required(trigger_server, "host", "config.trigger_server"), "config.trigger_server.host"),
            _port(_required(trigger_server, "port", "config.trigger_server"), "config.trigger_server.port")),
        web_server=ServerConfig(
            _string(_required(web_server, "host", "config.web_server"), "config.web_server.host"),
            _port(_required(web_server, "port", "config.web_server"), "config.web_server.port")),
        storage=StorageConfig(_string(_required(storage, "temp_dir", "config.storage"), "config.storage.temp_dir")),
        logging=LoggingConfig(_string(_required(logging, "path", "config.logging"), "config.logging.path")),
    )


def load_secrets(path: str | Path, config: AgentConfig) -> SecretsConfig:
    root = load_yaml(path)
    raw_recorders = _required(root, "recorders", "secrets")
    if raw_recorders is None:
        raw_recorders = {}
    recorder_values = _mapping(raw_recorders, "secrets.recorders")
    secrets: dict[str, RecorderSecret] = {}
    for recorder in config.recorders:
        raw = recorder_values.get(recorder.id)
        if raw is None:
            raise ConfigError(f"missing secrets.recorders.{recorder.id}")
        item = _mapping(raw, f"secrets.recorders.{recorder.id}")
        secrets[recorder.id] = RecorderSecret(_string(_required(item, "password", f"secrets.recorders.{recorder.id}"), f"secrets.recorders.{recorder.id}.password"))

    clip_server = _mapping(_required(root, "clip_server", "secrets"), "secrets.clip_server")
    oauth = _mapping(_required(clip_server, "oauth", "secrets.clip_server"), "secrets.clip_server.oauth")
    return SecretsConfig(
        recorders=secrets,
        client_id=_string(_required(oauth, "client_id", "secrets.clip_server.oauth"), "secrets.clip_server.oauth.client_id"),
        client_secret=_string(_required(oauth, "client_secret", "secrets.clip_server.oauth"), "secrets.clip_server.oauth.client_secret"),
    )
