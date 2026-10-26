import logging
import os
import socket
import subprocess
import sys
import threading
import time
import uuid

import pytest
import redis
from fastapi import HTTPException

from app import config, ratelimit
from app.ratelimit import MemoryBackend, RateLimitUnavailable, RateResult, RedisBackend


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def fresh_backend():
    ratelimit.use_backend(None)
    yield
    ratelimit.use_backend(None)


def name():
    return "t-" + uuid.uuid4().hex


# --- memory ---------------------------------------------------------------------


def test_hits_up_to_the_limit_are_allowed_and_the_next_is_not():
    clock = Clock()
    backend = MemoryBackend(clock)
    for _ in range(3):
        assert backend.hit("k", 3, 60) == RateResult(True, 0)
    refused = backend.hit("k", 3, 60)
    assert refused.allowed is False and refused.retry_after == 60


def test_retry_after_counts_down_and_is_rounded_up():
    clock = Clock()
    backend = MemoryBackend(clock)
    backend.hit("k", 1, 60)
    clock.advance(10)
    assert backend.hit("k", 1, 60).retry_after == 50
    clock.advance(49.2)
    assert backend.hit("k", 1, 60).retry_after == 1  # 0.8 s left: never 0 for a refusal


def test_the_window_ends_exactly_after_window_seconds():
    clock = Clock()
    backend = MemoryBackend(clock)
    backend.hit("k", 1, 60)
    clock.advance(59.999)
    assert backend.hit("k", 1, 60).allowed is False
    clock.advance(0.001)
    assert backend.hit("k", 1, 60).allowed is True


def test_refused_hits_do_not_extend_the_window():
    clock = Clock()
    backend = MemoryBackend(clock)
    backend.hit("k", 1, 60)
    for _ in range(20):
        clock.advance(2)
        assert backend.hit("k", 1, 60).allowed is False
    clock.advance(20)  # 60 s after the first hit
    assert backend.hit("k", 1, 60).allowed is True


def test_keys_and_buckets_are_counted_apart():
    backend = MemoryBackend(Clock())
    assert backend.hit("rl:a:1", 1, 60).allowed
    assert not backend.hit("rl:a:1", 1, 60).allowed
    assert backend.hit("rl:a:2", 1, 60).allowed
    assert backend.hit("rl:b:1", 1, 60).allowed


def test_expired_entries_are_swept_when_the_table_grows(monkeypatch):
    clock = Clock()
    backend = MemoryBackend(clock)
    monkeypatch.setattr(MemoryBackend, "SWEEP_ABOVE", 50)
    for i in range(60):
        backend.hit(f"old{i}", 1, 10)
    clock.advance(11)
    backend.hit("new", 1, 10)
    assert len(backend._entries) == 1


def test_a_swept_table_keeps_the_live_counters(monkeypatch):
    clock = Clock()
    backend = MemoryBackend(clock)
    monkeypatch.setattr(MemoryBackend, "SWEEP_ABOVE", 5)
    backend.hit("live", 1, 1000)
    for i in range(10):
        backend.hit(f"x{i}", 1, 1000)
    assert backend.hit("live", 1, 1000).allowed is False


def test_threads_cannot_get_more_than_the_limit_through():
    backend = MemoryBackend()
    allowed = []

    def work():
        for _ in range(50):
            allowed.append(backend.hit("k", 100, 60).allowed)

    threads = [threading.Thread(target=work) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(allowed) == 1000 and sum(allowed) == 100


class SlowDict(dict):
    """Reading takes a moment, so two threads that are not locked out will interleave."""

    def get(self, *args):
        value = super().get(*args)
        time.sleep(0.0005)
        return value


def test_the_lock_is_what_keeps_the_count_exact():
    backend = MemoryBackend()
    backend._entries = SlowDict()
    allowed = []

    def work():
        for _ in range(10):
            allowed.append(backend.hit("k", 40, 60).allowed)

    threads = [threading.Thread(target=work) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(allowed) == 120 and sum(allowed) == 40


def test_clear_forgets_everything():
    backend = MemoryBackend(Clock())
    backend.hit("k", 1, 60)
    backend.clear()
    assert backend.hit("k", 1, 60).allowed


# --- the frozen interface -------------------------------------------------------


def test_hit_without_redis_url_counts_in_memory(monkeypatch):
    monkeypatch.setattr(config, "REDIS_URL", "")
    key = name()
    assert ratelimit.hit("b", key, 2, 60) == RateResult(True, 0)
    assert ratelimit.hit("b", key, 2, 60).allowed
    result = ratelimit.hit("b", key, 2, 60)
    assert not result.allowed and 1 <= result.retry_after <= 60
    allowed, retry_after = result  # still unpacks
    assert allowed is False and isinstance(retry_after, int)


@pytest.mark.parametrize("limit,window", [(0, 60), (-1, 60), (5, 0), (5, -3)])
def test_nonsense_limits_are_a_programming_error(limit, window):
    with pytest.raises(ValueError):
        ratelimit.hit("b", "k", limit, window)


def test_use_backend_none_starts_again_with_empty_counters():
    ratelimit.hit("b", "same", 1, 60)
    assert not ratelimit.hit("b", "same", 1, 60).allowed
    ratelimit.use_backend(None)
    assert ratelimit.hit("b", "same", 1, 60).allowed


def test_the_backend_follows_redis_url(monkeypatch):
    monkeypatch.setattr(config, "REDIS_URL", "redis://localhost:1/0")
    assert isinstance(ratelimit._get_backend(), RedisBackend)
    ratelimit.use_backend(None)
    monkeypatch.setattr(config, "REDIS_URL", "")
    assert isinstance(ratelimit._get_backend(), MemoryBackend)


def test_enforce_is_silent_below_the_limit_and_a_429_above_it():
    ratelimit.enforce("b", "k", 1, 60)
    with pytest.raises(HTTPException) as caught:
        ratelimit.enforce("b", "k", 1, 60)
    exc = caught.value
    assert exc.status_code == 429 and exc.detail == "RATE_LIMITED"
    assert 1 <= int(exc.headers["Retry-After"]) <= 60


def test_unavailable_passes_through_enforce():
    class Broken:
        def hit(self, *a):
            raise RateLimitUnavailable()

    ratelimit.use_backend(Broken())
    with pytest.raises(RateLimitUnavailable):
        ratelimit.enforce("b", "k", 1, 60)


# --- redis ----------------------------------------------------------------------

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "")
needs_redis = pytest.mark.skipif(not REDIS_TEST_URL, reason="REDIS_TEST_URL is not set")


@pytest.fixture
def real():
    backend = RedisBackend(REDIS_TEST_URL)
    yield backend
    client = backend._client
    for key in client.scan_iter("rl:t-*"):
        client.delete(key)


@needs_redis
def test_redis_counts_like_memory(real):
    n = "rl:" + name()
    for _ in range(3):
        assert real.hit(n, 3, 60) == RateResult(True, 0)
    refused = real.hit(n, 3, 60)
    assert refused.allowed is False and 58 <= refused.retry_after <= 60


@needs_redis
def test_redis_keeps_keys_apart(real):
    a, b = "rl:" + name(), "rl:" + name()
    assert real.hit(a, 1, 60).allowed and not real.hit(a, 1, 60).allowed
    assert real.hit(b, 1, 60).allowed


@needs_redis
def test_redis_sets_an_expiry_and_refused_hits_do_not_extend_it(real):
    n = "rl:" + name()
    real.hit(n, 1, 100)
    first = real._client.pttl(n)
    assert 0 < first <= 100_000
    time.sleep(0.3)
    for _ in range(5):
        real.hit(n, 1, 100)
    assert real._client.pttl(n) < first


@needs_redis
def test_redis_window_really_ends(real):
    n = "rl:" + name()
    assert real.hit(n, 1, 1).allowed
    assert not real.hit(n, 1, 1).allowed
    time.sleep(1.1)
    assert real.hit(n, 1, 1).allowed


@needs_redis
def test_a_counter_that_lost_its_expiry_heals(real):
    n = "rl:" + name()
    real._client.set(n, 7)  # no TTL: would block this key forever
    result = real.hit(n, 5, 30)
    assert result.allowed is False
    assert 0 < real._client.pttl(n) <= 30_000


@needs_redis
def test_redis_is_atomic_under_threads(real):
    n = "rl:" + name()
    allowed = []

    def work():
        backend = RedisBackend(REDIS_TEST_URL)
        for _ in range(25):
            allowed.append(backend.hit(n, 60, 60).allowed)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(allowed) == 200 and sum(allowed) == 60


@needs_redis
def test_the_public_hit_uses_the_rl_prefix(monkeypatch, real):
    monkeypatch.setattr(config, "REDIS_URL", REDIS_TEST_URL)
    ratelimit.use_backend(None)
    key = name()
    ratelimit.hit("t-bucket", key, 5, 60)
    assert real._client.exists(f"rl:t-bucket:{key}") == 1
    ratelimit.use_backend(None)


@needs_redis
def test_a_key_of_the_wrong_type_is_unavailable_not_allowed(real):
    n = "rl:" + name()
    real._client.lpush(n, "x")
    with pytest.raises(RateLimitUnavailable):
        real.hit(n, 5, 60)


# --- redis failing: closed, never open ------------------------------------------


def test_redis_connections_have_short_timeouts():
    kwargs = RedisBackend("redis://127.0.0.1:1/0")._client.connection_pool.connection_kwargs
    assert kwargs["socket_connect_timeout"] == 1 and kwargs["socket_timeout"] == 1


def test_an_unreachable_redis_is_unavailable_and_quick():
    backend = RedisBackend("redis://127.0.0.1:1/0")
    started = time.monotonic()
    with pytest.raises(RateLimitUnavailable):
        backend.hit("rl:x", 5, 60)
    assert time.monotonic() - started < 3


def test_a_redis_that_never_answers_times_out_as_unavailable():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    try:
        backend = RedisBackend(f"redis://127.0.0.1:{server.getsockname()[1]}/0")
        started = time.monotonic()
        with pytest.raises(RateLimitUnavailable):
            backend.hit("rl:x", 5, 60)
        assert time.monotonic() - started < 4
    finally:
        server.close()


class FakeScript:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def __call__(self, keys, args):
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, script):
        self.script = script

    def register_script(self, _):
        return self.script


@pytest.mark.parametrize(
    "script",
    [
        FakeScript(error=redis.ConnectionError("down")),
        FakeScript(error=redis.TimeoutError("slow")),
        FakeScript(error=redis.ResponseError("OOM")),
        FakeScript(error=redis.BusyLoadingError("loading")),
        FakeScript(error=OSError("socket")),
        FakeScript(result=None),
        FakeScript(result=["not", "numbers"]),
        FakeScript(result=[1]),
    ],
    ids=["connection", "timeout", "response", "loading", "os", "none", "garbage", "short"],
)
def test_every_kind_of_redis_failure_is_unavailable(script):
    with pytest.raises(RateLimitUnavailable):
        RedisBackend(client=FakeClient(script)).hit("rl:x", 5, 60)


def test_other_errors_are_not_hidden():
    with pytest.raises(KeyError):
        RedisBackend(client=FakeClient(FakeScript(error=KeyError("bug")))).hit("rl:x", 5, 60)


def test_the_outage_is_logged_once_in_a_while_not_per_request(caplog, monkeypatch):
    monkeypatch.setattr(ratelimit, "_last_warning", 0.0)
    backend = RedisBackend(client=FakeClient(FakeScript(error=redis.ConnectionError("down"))))
    with caplog.at_level(logging.WARNING, logger="tcancy.ratelimit"):
        for _ in range(5):
            with pytest.raises(RateLimitUnavailable):
                backend.hit("rl:x", 5, 60)
    assert len([r for r in caplog.records if "unavailable" in r.getMessage()]) == 1
    assert "down" not in caplog.text and "127" not in caplog.text  # no addresses or secrets in the log


def test_the_redis_url_is_not_part_of_the_configuration_error():
    done = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env={**os.environ, "REDIS_URL": "http://user:s3cretpass@host:6379/0"}, capture_output=True, text=True,
    )
    assert done.returncode != 0
    assert "REDIS_URL must start with redis://" in done.stderr
    assert "s3cretpass" not in done.stderr


@pytest.mark.parametrize("url", ["redis://h:6379/0", "rediss://h:6380/0", "unix:///tmp/redis.sock", ""])
def test_valid_redis_urls_load(url):
    done = subprocess.run(
        [sys.executable, "-c", "import app.config"], env={**os.environ, "REDIS_URL": url},
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr