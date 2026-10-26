# STUB-RAYNALD
"""Rate limiting.

Interface-stub stage: hit() always allows. The real implementation uses Redis (REDIS_URL),
counts in-process when REDIS_URL is empty, and raises RateLimitUnavailable when Redis fails.
"""
from typing import NamedTuple


class RateResult(NamedTuple):
    allowed: bool
    retry_after: int


class RateLimitUnavailable(Exception):
    """Raised by hit() when the rate-limit backend (Redis) cannot be reached."""


# STUB-RAYNALD
def hit(bucket: str, key: str, limit: int, window_seconds: int) -> RateResult:
    """Frozen interface: count one hit. retry_after is in seconds. The stub always allows."""
    return RateResult(allowed=True, retry_after=0)