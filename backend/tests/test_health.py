from sqlalchemy import text

from app.db import engine


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_uses_test_database():
    with engine.connect() as conn:
        name = conn.execute(text("SELECT current_database()")).scalar()
    assert name.endswith("_test")
