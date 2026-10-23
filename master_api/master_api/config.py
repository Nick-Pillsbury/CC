"""Validated runtime configuration for downstream service clients."""

from dataclasses import dataclass
from os import environ
from typing import Mapping
from urllib.parse import urlsplit

import httpx


class ConfigurationError(ValueError):
    """Raised when Master API environment configuration is invalid."""


def _positive_float(values: Mapping[str, str], name: str, default: float) -> float:
    raw_value = values.get(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _http_base_url(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name, default).rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"{name} must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment:
        raise ConfigurationError(f"{name} cannot contain a query or fragment")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings needed to choose and configure downstream clients."""

    client_mode: str = "mock"
    hardware_base_url: str = "http://hardware:8000"
    video_base_url: str = "http://video:8000"
    connect_timeout_seconds: float = 0.5
    read_timeout_seconds: float = 0.5
    write_timeout_seconds: float = 0.5
    pool_timeout_seconds: float = 0.5

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Settings":
        source = environ if values is None else values
        mode = source.get("MASTER_API_CLIENT_MODE", "mock").lower()
        if mode not in {"mock", "http"}:
            raise ConfigurationError(
                "MASTER_API_CLIENT_MODE must be either 'mock' or 'http'"
            )

        return cls(
            client_mode=mode,
            hardware_base_url=_http_base_url(
                source,
                "MASTER_API_HARDWARE_BASE_URL",
                "http://hardware:8000",
            ),
            video_base_url=_http_base_url(
                source,
                "MASTER_API_VIDEO_BASE_URL",
                "http://video:8000",
            ),
            connect_timeout_seconds=_positive_float(
                source, "MASTER_API_HTTP_CONNECT_TIMEOUT_SECONDS", 0.5
            ),
            read_timeout_seconds=_positive_float(
                source, "MASTER_API_HTTP_READ_TIMEOUT_SECONDS", 0.5
            ),
            write_timeout_seconds=_positive_float(
                source, "MASTER_API_HTTP_WRITE_TIMEOUT_SECONDS", 0.5
            ),
            pool_timeout_seconds=_positive_float(
                source, "MASTER_API_HTTP_POOL_TIMEOUT_SECONDS", 0.5
            ),
        )

    def http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )
