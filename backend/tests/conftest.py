import os
import shutil
import tempfile

import pytest

_test_url = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://tcancy:tcancy@db:5432/tcancy_test"
)
_db_name = _test_url.rsplit("/", 1)[-1].split("?")[0]
assert _db_name.endswith("_test"), "TEST_DATABASE_URL must point to a database ending in _test"

os.environ.setdefault("SESSION_SECRET", "test-only-secret-not-for-production-use-0123456789")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("MASTER_KEY", "dGNhbmN5LXRlc3QtbWFzdGVyLWtleS0wMTIzNDU2Nzg=")
os.environ.setdefault("BLIND_INDEX_KEY", "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f")
os.environ["DATABASE_URL"] = _test_url
os.environ["REDIS_URL"] = ""
os.environ["TRUSTED_PROXIES"] = ""
for _name in [n for n in os.environ if n.startswith("RATE_")]:
    del os.environ[_name]
_upload_dir = tempfile.mkdtemp(prefix="tcancy_uploads_")
os.environ["UPLOAD_DIR"] = _upload_dir

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_plain_request = TestClient.request


def _request_with_csrf(self, method, url, *args, **kwargs):
    if getattr(self, "auto_csrf", True) and method.upper() in _UNSAFE_METHODS:
        headers = dict(kwargs.get("headers") or {})
        if not any(name.lower() == "x-csrf-token" for name in headers):
            token = next((c.value for c in self.cookies.jar if c.name == "csrf_token"), None)
            if token:
                headers["X-CSRF-Token"] = token
        kwargs["headers"] = headers
    return _plain_request(self, method, url, *args, **kwargs)


TestClient.request = _request_with_csrf


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # The 40 starter skills normally come from the migration; seed them here.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO skills (name) SELECT 'Skill ' || g FROM generate_series(1, 40) g"
        ))
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    shutil.rmtree(_upload_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_tables(schema):
    yield
    for entry in os.listdir(_upload_dir):
        path = os.path.join(_upload_dir, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    names = ", ".join(
        '"%s"' % t.name for t in Base.metadata.sorted_tables if t.name != "skills"
    )
    if names:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE " + names + " RESTART IDENTITY CASCADE"))

@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with empty rate-limit counters."""
    ratelimit.use_backend(None)
    yield
    ratelimit.use_backend(None)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
