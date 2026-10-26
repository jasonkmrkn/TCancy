import ipaddress
import os
from urllib.parse import urlsplit

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

def _origin_env(name, default):
    """One origin: scheme + host [+ port]. Returned in the form browsers send in `Origin`."""
    raw = os.environ.get(name, "").strip() or default
    problem = f"{name} must be a single origin such as https://example.com (no path, no trailing slash), got {raw!r}"
    if "," in raw or any(c.isspace() for c in raw):
        raise ValueError(problem)
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise ValueError(problem) from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(problem)
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError(problem)
    host = parts.hostname  
    if not all(c in "abcdefghijklmnopqrstuvwxyz0123456789.-_:" for c in host):
        raise ValueError(problem)  
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{host}" + (f":{port}" if port not in (None, default_port) else "")

def _proxies_env(name):
    """Addresses or CIDR ranges of the reverse proxies allowed to set X-Forwarded-For."""
    nets = []
    for item in os.environ.get(name, "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            net = ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise ValueError(f"{name} must be a comma-separated list of IP addresses or CIDR ranges, got {item!r}") from None
        if net.prefixlen == 0:
            raise ValueError(f"{name} must not trust every address ({item!r}); list only your own proxies")
        nets.append(net)
    return tuple(nets)

def _redis_url_env(name):
    raw = os.environ.get(name, "").strip()
    if raw and urlsplit(raw).scheme not in ("redis", "rediss", "unix"):
        raise ValueError(f"{name} must start with redis://, rediss:// or unix://")
    return raw

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tcancy:tcancy@localhost:5433/tcancy"
)
FRONTEND_ORIGIN = _origin_env("FRONTEND_ORIGIN", "http://localhost:3000")
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

# Test database. Must end with _test; enforced by tests/conftest.py, not here.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").strip().lower() not in ("0", "false", "no")

REDIS_URL = _redis_url_env("REDIS_URL")

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "")

TRUSTED_PROXIES = _proxies_env("TRUSTED_PROXIES")

REGISTER_LIMIT = _int_env("RATE_REGISTER_LIMIT", 10, 1, 1_000_000)
REGISTER_WINDOW_SECONDS = _int_env("RATE_REGISTER_WINDOW_SECONDS", 3600, 1, 86_400)
LOGIN_IP_LIMIT = _int_env("RATE_LOGIN_IP_LIMIT", 60, 1, 1_000_000)
LOGIN_IP_WINDOW_SECONDS = _int_env("RATE_LOGIN_IP_WINDOW_SECONDS", 60, 1, 86_400)
LOGIN_USER_LIMIT = _int_env("RATE_LOGIN_USER_LIMIT", 5, 1, 1_000_000)
LOGIN_USER_WINDOW_SECONDS = _int_env("RATE_LOGIN_USER_WINDOW_SECONDS", 60, 1, 86_400)
DELETE_ACCOUNT_LIMIT = _int_env("RATE_DELETE_ACCOUNT_LIMIT", 5, 1, 1_000_000)
DELETE_ACCOUNT_WINDOW_SECONDS = _int_env("RATE_DELETE_ACCOUNT_WINDOW_SECONDS", 60, 1, 86_400)