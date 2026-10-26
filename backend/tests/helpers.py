import itertools

from functools import cache

from sqlalchemy import text

from app import security

from app.db import engine

_counter = itertools.count(1)

@cache
def password_hash(password="rahasia123"):
    """Argon2 hash of `password`, computed once per test run.

    For users inserted with raw SQL, which must now fill password_hash.
    """
    return security.hash_password(password)


def skill_ids(n=2):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM skills ORDER BY name LIMIT :n"), {"n": n}).all()
    return [str(r[0]) for r in rows]


def make_profile(**over):
    """A valid applicant profile with a unique email and NIK."""
    n = next(_counter)
    data = {
        "full_name": "Budi Santoso",
        "email": "budi%d@example.com" % n,
        "phone": "+628123456789",
        "nik": "%016d" % n,
        "address": "Jl. Keputih, Surabaya",
        "birth_date": "2000-05-17",
        "angkatan": 2019,
        "skill_ids": skill_ids(),
        "preferred_type": "internship",
        "preferred_location": "Surabaya",
    }
    data.update(over)
    return data


# STUB-RAYNALD
def login_as(client, username, password="rahasia123"):
    """Log in and return the headers non-GET requests need (CSRF).

    Frozen interface: the shape is {"X-CSRF-Token": <value of the csrf_token cookie>}.
    """
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies["csrf_token"]}