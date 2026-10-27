
import itertools

import pytest

from app import config, ratelimit
from test_ratelimit_endpoints import from_address, login, register

ADDRESS = "198.51.100.7"
OTHER_ADDRESS = "203.0.113.9"
THIRD_ADDRESS = "192.0.2.44"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    fake = Clock()
    ratelimit.use_backend(ratelimit.MemoryBackend(clock=fake))
    return fake  # the autouse fixture in conftest resets the backend after the test


@pytest.fixture
def stranger():
    """A different username every time: unknown accounts, so each login is a plain 401."""
    numbers = itertools.count()
    return lambda: "nobody%d" % next(numbers)


def refused(r):
    assert r.status_code == 429, r.text
    assert r.json() == {"detail": "RATE_LIMITED"}
    assert "set-cookie" not in r.headers
    return int(r.headers["retry-after"])


def test_the_defaults_this_file_relies_on_are_the_documented_ones():
    assert (config.LOGIN_IP_LIMIT, config.LOGIN_IP_WINDOW_SECONDS) == (60, 60)
    assert (config.LOGIN_USER_LIMIT, config.LOGIN_USER_WINDOW_SECONDS) == (5, 60)


def test_the_61st_login_in_a_minute_from_one_address_is_refused(clock, stranger):
    with from_address(ADDRESS) as c:
        for n in range(60):
            r = login(c, stranger())
            assert r.status_code == 401, "request %d: %s" % (n + 1, r.text)
        for _ in range(2):  # the 61st and the 62nd
            assert 1 <= refused(login(c, stranger())) <= 60


def test_the_6th_try_for_one_username_in_a_minute_is_refused_long_before_the_address_limit(clock, stranger):
    with from_address(ADDRESS) as c:
        for n in range(5):
            r = login(c, "budi")
            assert r.status_code == 401, "try %d: %s" % (n + 1, r.text)
        assert 1 <= refused(login(c, "budi")) <= 60
        assert login(c, stranger()).status_code == 401  # other usernames from this address still work


def test_retry_after_counts_down_with_the_window(clock, stranger):
    with from_address(ADDRESS) as c:
        for _ in range(60):
            assert login(c, stranger()).status_code == 401
        assert refused(login(c, stranger())) == 60
        clock.now += 25
        assert refused(login(c, stranger())) == 35
        clock.now += 34
        assert refused(login(c, stranger())) == 1


def test_a_new_window_starts_a_new_budget_of_60(clock, stranger):
    with from_address(ADDRESS) as c:
        for _ in range(60):
            assert login(c, stranger()).status_code == 401
        clock.now += 59
        assert refused(login(c, stranger())) == 1
        clock.now += 1  # exactly 60 seconds after the first request of the window
        for n in range(60):
            r = login(c, stranger())
            assert r.status_code == 401, "request %d of the new window: %s" % (n + 1, r.text)
        assert 1 <= refused(login(c, stranger())) <= 60


def test_another_address_is_not_affected(clock, stranger):
    with from_address(ADDRESS) as c, from_address(OTHER_ADDRESS) as other:
        for _ in range(60):
            assert login(c, stranger()).status_code == 401
        refused(login(c, stranger()))
        for _ in range(5):
            assert login(other, stranger()).status_code == 401


def test_the_right_password_does_not_get_past_the_limit(clock, stranger):
    with from_address(THIRD_ADDRESS) as c:
        assert register(c, "budi").status_code == 201
    with from_address(ADDRESS) as c, from_address(OTHER_ADDRESS) as other:
        for _ in range(60):
            assert login(c, stranger()).status_code == 401
        refused(login(c, "budi"))  # correct password, still refused, and no session cookie
        assert login(other, "budi").status_code == 200


def test_a_forged_forwarding_header_is_not_a_way_around_the_limit(clock, stranger):
    forged = itertools.count(1)
    with from_address(ADDRESS) as c:
        for _ in range(60):
            r = login(c, stranger(), headers={"X-Forwarded-For": "10.9.8.%d" % next(forged)})
            assert r.status_code == 401
        refused(login(c, stranger(), headers={"X-Forwarded-For": "10.9.8.250"}))