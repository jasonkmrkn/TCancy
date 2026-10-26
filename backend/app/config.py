import os

def _int_env(name, default, lo=None, hi=None):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if lo is not None and value < lo:
        raise ValueError(f"{name} must be >= {lo}, got {value}")
    if hi is not None and value > hi:
        raise ValueError(f"{name} must be <= {hi}, got {value}")
    return value

def _choice_env(name, default, allowed):
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}, got {raw!r}")
    return raw

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tcancy:tcancy@localhost:5433/tcancy"
)
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")

# base64 of 32 byte (openssl rand -base64 32)
MASTER_KEY = os.environ.get("MASTER_KEY", "")
# hex of 32 byte (openssl rand -hex 32)
BLIND_INDEX_KEY = os.environ.get("BLIND_INDEX_KEY", "")

IDENTITY_ACCESS_DAYS = _int_env("IDENTITY_ACCESS_DAYS", 28, 1, 365)
DOWNLOAD_LIMIT_PER_HOUR = _int_env("DOWNLOAD_LIMIT_PER_HOUR", 20)
ACCESS_REMINDER_DAYS = _int_env("ACCESS_REMINDER_DAYS", 3, 1, 30)

ENCRYPTION_POLICY = _choice_env("ENCRYPTION_POLICY", "assignment", ("assignment", "production"))
INTEGRITY_MODE = _choice_env("INTEGRITY_MODE", "off", ("off", "log-only", "enforce"))

# Empty means the rate limiter runs in-process.
REDIS_URL = os.environ.get("REDIS_URL", "")
# Redis used only by tests.
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "")

# Test database. Must end with _test; enforced by tests/conftest.py, not here.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").strip().lower() not in ("0", "false", "no")
