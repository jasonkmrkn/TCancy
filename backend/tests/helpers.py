import itertools

from sqlalchemy import text

from app.db import engine

_counter = itertools.count(1)


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
