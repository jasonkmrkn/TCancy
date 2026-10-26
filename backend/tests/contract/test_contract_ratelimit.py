"""Contract for app.ratelimit: the shape of the result of hit()."""
import uuid

from app import ratelimit


def _key():
    return "contract-" + uuid.uuid4().hex


def test_hit_returns_a_rate_result():
    result = ratelimit.hit("contract", _key(), 100, 60)
    assert isinstance(result, ratelimit.RateResult)
    assert isinstance(result.allowed, bool)
    assert isinstance(result.retry_after, int)
    assert result.retry_after >= 0


def test_one_hit_below_the_limit_is_allowed():
    assert ratelimit.hit("contract", _key(), 100, 60).allowed is True


def test_result_can_be_unpacked():
    allowed, retry_after = ratelimit.hit("contract", _key(), 100, 60)
    assert allowed is True
    assert isinstance(retry_after, int)


def test_unavailable_is_an_exception():
    assert issubclass(ratelimit.RateLimitUnavailable, Exception)