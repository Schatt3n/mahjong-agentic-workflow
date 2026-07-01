from __future__ import annotations

import os
import pathlib
from collections.abc import Callable
from urllib.parse import urlparse

from .redis_cache import RedisCache, RedisCacheError


DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


def trial_cache_prefix_from_env(default: str = "mahjong:trial") -> str:
    return os.environ.get("MAHJONG_CACHE_PREFIX", default).strip(":") or default


def build_redis_cache_from_env(
    *,
    default_url: str = DEFAULT_REDIS_URL,
    printer: Callable[[str], None] = print,
) -> RedisCache | None:
    redis_url = os.environ.get("MAHJONG_REDIS_URL", default_url).strip()
    if redis_url.lower() in {"", "0", "false", "off", "none", "disabled"}:
        printer("Redis cache disabled by MAHJONG_REDIS_URL.")
        return None
    timeout = float(os.environ.get("MAHJONG_REDIS_TIMEOUT_SECONDS", "0.3"))
    try:
        cache = RedisCache.from_url(redis_url, timeout_seconds=timeout)
        cache.ping()
    except (RedisCacheError, ValueError) as exc:
        printer(f"Redis cache unavailable, continue with SQLite only: {exc}")
        return None
    printer(f"Redis cache enabled: {redact_redis_url(redis_url)}")
    return cache


def redact_redis_url(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    if not parsed.password:
        return redis_url
    username = parsed.username or ""
    auth = f"{username}:***@" if username else "***@"
    host = parsed.hostname or "127.0.0.1"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{auth}{host}{port}{parsed.path or ''}"


def load_local_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
