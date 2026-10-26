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
_upload_dir = tempfile.mkdtemp(prefix="tcancy_uploads_")
os.environ["UPLOAD_DIR"] = _upload_dir

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


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
        os.remove(os.path.join(_upload_dir, entry))
    names = ", ".join(
        '"%s"' % t.name for t in Base.metadata.sorted_tables if t.name != "skills"
    )
    if names:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE " + names + " RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
