import os
import subprocess
import sys

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import config, limits, ratelimit
from app.ratelimit import MemoryBackend, RateLimitUnavailable


class Recording(MemoryBackend):
    def __init__(self):
        super().__init__()
        self.names = []

    def hit(self, name, limit, window_seconds):
        self.names.append((name, limit, window_seconds))
        return super().hit(name, limit, window_seconds)


@pytest.fixture
def backend():
    b = Recording()
    ratelimit.use_backend(b)
    yield b
    ratelimit.use_backend(None)


def req(peer="203.0.113.9"):
    return Request({"type": "http", "client": (peer, 5000), "headers": []})


def refused(call, *args):
    with pytest.raises(HTTPException) as caught:
        call(*args)
    assert caught.value.status_code == 429 and caught.value.detail == "RATE_LIMITED"
    return caught.value


def test_the_defaults_are_the_spec():
    assert (config.REGISTER_LIMIT, config.REGISTER_WINDOW_SECONDS) == (10, 3600)
    assert (config.LOGIN_IP_LIMIT, config.LOGIN_IP_WINDOW_SECONDS) == (60, 60)
    assert (config.LOGIN_USER_LIMIT, config.LOGIN_USER_WINDOW_SECONDS) == (5, 60)
    assert (config.DELETE_ACCOUNT_LIMIT, config.DELETE_ACCOUNT_WINDOW_SECONDS) == (5, 60)


# --- register -------------------------------------------------------------------


def test_register_allows_ten_per_address_then_refuses_with_retry_after(backend):
    for _ in range(10):
        limits.register(req())
    exc = refused(limits.register, req())
    assert 3590 <= int(exc.headers["Retry-After"]) <= 3600
    limits.register(req("203.0.113.10"))  # another address is unaffected


def test_register_is_one_bucket_per_address(backend):
    limits.register(req())
    assert [n for n, *_ in backend.names] == ["rl:register:203.0.113.9"]


# --- login ----------------------------------------------------------------------


def test_login_allows_five_per_address_and_username_a_minute(backend):
    for _ in range(5):
        limits.login(req(), "budi")
    exc = refused(limits.login, req(), "budi")
    assert 1 <= int(exc.headers["Retry-After"]) <= 60
    limits.login(req(), "siti")  # same address, another account
    limits.login(req("203.0.113.10"), "budi")  # same account, another address


def test_login_allows_sixty_per_address_a_minute(backend):
    for i in range(60):
        limits.login(req(), f"user{i}")
    refused(limits.login, req(), "user60")
    limits.login(req("203.0.113.10"), "user60")


def test_the_address_is_checked_first_and_a_refusal_there_spares_the_user_budget(backend):
    for i in range(60):
        limits.login(req(), f"user{i}")
    backend.names.clear()
    refused(limits.login, req(), "budi")
    assert [n.split(":")[1] for n, *_ in backend.names] == ["login_ip"]


def test_the_user_key_is_hashed_and_ignores_case_and_spaces(backend):
    limits.login(req(), "Budi ")
    limits.login(req(), "budi")
    keys = [n for n, *_ in backend.names if n.startswith("rl:login_user:")]
    assert len(keys) == 2 and keys[0] == keys[1]
    assert "budi" not in keys[0].lower().replace("login_user", "")
    assert keys[0].startswith("rl:login_user:203.0.113.9|") and len(keys[0].split("|")[1]) == 64


def test_every_attempt_counts_whether_it_succeeds_or_not(backend):
    # limits.login knows nothing of the outcome: one call per attempt, so a login that
    # worked uses up the budget like one that failed.
    for _ in range(5):
        limits.login(req(), "budi")
    refused(limits.login, req(), "budi")


def test_a_client_cannot_spend_another_clients_budget_for_the_same_account(backend):
    for _ in range(5):
        limits.login(req("198.51.100.1"), "victim")
    refused(limits.login, req("198.51.100.1"), "victim")
    limits.login(req("198.51.100.2"), "victim")


# --- delete account -------------------------------------------------------------


def test_delete_account_allows_five_a_minute_per_address_and_user(backend):
    for _ in range(5):
        limits.delete_account(req(), "u-1")
    refused(limits.delete_account, req(), "u-1")
    limits.delete_account(req(), "u-2")
    limits.delete_account(req("203.0.113.10"), "u-1")
    assert backend.names[0][0] == "rl:delete_account:203.0.113.9|u-1"


# --- the numbers come from config, at call time ---------------------------------


def test_limits_follow_config(backend, monkeypatch):
    monkeypatch.setattr(config, "REGISTER_LIMIT", 2)
    monkeypatch.setattr(config, "REGISTER_WINDOW_SECONDS", 30)
    limits.register(req())
    limits.register(req())
    exc = refused(limits.register, req())
    assert int(exc.headers["Retry-After"]) <= 30


def test_ipv6_clients_share_a_budget_per_network(backend):
    for i in range(10):
        limits.register(req(f"2001:db8:1:2::{i + 1}"))
    refused(limits.register, req("2001:db8:1:2:ffff::1"))
    limits.register(req("2001:db8:1:3::1"))


def test_an_unavailable_backend_is_not_swallowed(backend):
    class Broken:
        def hit(self, *a):
            raise RateLimitUnavailable()

    ratelimit.use_backend(Broken())
    with pytest.raises(RateLimitUnavailable):
        limits.login(req(), "budi")


# --- overriding the numbers through the environment -----------------------------


def read(**env):
    code = "from app import config as c; print(c.REGISTER_LIMIT, c.REGISTER_WINDOW_SECONDS, c.LOGIN_IP_LIMIT, c.LOGIN_USER_LIMIT, c.LOGIN_USER_WINDOW_SECONDS, c.DELETE_ACCOUNT_LIMIT)"
    return subprocess.run([sys.executable, "-c", code], env={**os.environ, **env}, capture_output=True, text=True)


def test_every_limit_and_window_can_be_overridden():
    done = read(
        RATE_REGISTER_LIMIT="1000", RATE_REGISTER_WINDOW_SECONDS="10", RATE_LOGIN_IP_LIMIT="7",
        RATE_LOGIN_USER_LIMIT="9", RATE_LOGIN_USER_WINDOW_SECONDS="30", RATE_DELETE_ACCOUNT_LIMIT="2",
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["1000", "10", "7", "9", "30", "2"]


def test_unset_or_blank_variables_keep_the_defaults():
    done = read(RATE_REGISTER_LIMIT="  ")
    assert done.stdout.split() == ["10", "3600", "60", "5", "60", "5"]


@pytest.mark.parametrize("name", [
    "RATE_REGISTER_LIMIT", "RATE_REGISTER_WINDOW_SECONDS", "RATE_LOGIN_IP_LIMIT", "RATE_LOGIN_IP_WINDOW_SECONDS",
    "RATE_LOGIN_USER_LIMIT", "RATE_LOGIN_USER_WINDOW_SECONDS", "RATE_DELETE_ACCOUNT_LIMIT",
    "RATE_DELETE_ACCOUNT_WINDOW_SECONDS",
])
@pytest.mark.parametrize("value", ["0", "-5", "ten", "1.5", "99999999999"])
def test_a_nonsense_value_stops_the_app_with_the_variable_name(name, value):
    done = read(**{name: value})
    assert done.returncode != 0
    assert name in done.stderr