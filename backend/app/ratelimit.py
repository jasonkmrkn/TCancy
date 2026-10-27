import logging
import math
import threading
import time
from typing import NamedTuple

import redis
from fastapi import HTTPException

from app import config

log = logging.getLogger("tcancy.ratelimit")


class RateResult(NamedTuple):
    allowed: bool
    retry_after: int


class RateLimitUnavailable(Exception):
    """Raised by hit() when the rate-limit backend (Redis) cannot be reached."""


class MemoryBackend:
    """Counters in this process. Safe across threads (handlers run in a thread pool)."""

    SWEEP_ABOVE = 10_000  

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[int, float]] = {}  

    def hit(self, name: str, limit: int, window_seconds: int) -> RateResult:
        with self._lock:
            now = self._clock()
            if len(self._entries) > self.SWEEP_ABOVE:
                self._entries = {k: v for k, v in self._entries.items() if v[1] > now}
            count, expires_at = self._entries.get(name, (0, 0.0))
            if expires_at <= now:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._entries[name] = (count, expires_at)
        if count <= limit:
            return RateResult(True, 0)
        return RateResult(False, max(1, math.ceil(expires_at - now)))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_LUA_HIT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if count == 1 or ttl < 0 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""

_WARN_EVERY = 30.0  
_last_warning = 0.0


class RedisBackend:
    def __init__(self, url: str | None = None, client=None):
        self._client = client or redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        self._script = self._client.register_script(_LUA_HIT)

    def hit(self, name: str, limit: int, window_seconds: int) -> RateResult:
        try:
            count, ttl_ms = self._script(keys=[name], args=[window_seconds * 1000])
            count, ttl_ms = int(count), int(ttl_ms)
        except (redis.RedisError, OSError, TypeError, ValueError) as exc:
            _warn(exc)
            raise RateLimitUnavailable() from exc
        if count <= limit:
            return RateResult(True, 0)
        return RateResult(False, max(1, math.ceil(ttl_ms / 1000)))


def _warn(exc: Exception) -> None:
    global _last_warning
    now = time.monotonic()
    if now - _last_warning >= _WARN_EVERY:
        _last_warning = now
        log.warning("rate limit backend unavailable (%s): refusing requests that need it", type(exc).__name__)


_backend = None
_backend_lock = threading.Lock()


def _get_backend():
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = RedisBackend(config.REDIS_URL) if config.REDIS_URL else MemoryBackend()
    return _backend


def use_backend(backend) -> None:
    """Replace the backend (tests). None goes back to the one REDIS_URL asks for, with empty counters."""
    global _backend
    with _backend_lock:
        _backend = backend


def hit(bucket: str, key: str, limit: int, window_seconds: int) -> RateResult:
    """Frozen interface: count one hit. retry_after is in seconds, 0 when allowed."""
    if limit < 1 or window_seconds < 1:
        raise ValueError("limit and window_seconds must be at least 1")
    return _get_backend().hit(f"rl:{bucket}:{key}", limit, window_seconds)


def enforce(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """hit(), but a refused hit becomes the 429 the API answers with."""
    result = hit(bucket, key, limit, window_seconds)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="RATE_LIMITED",
            headers={"Retry-After": str(result.retry_after)},
        )