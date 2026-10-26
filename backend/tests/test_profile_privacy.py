import uuid

import pytest
from sqlalchemy import inspect, text

from app import blind_index, profiles
from app.db import engine
from helpers import make_profile

AUTH = "/api/v1/auth"
ME = "/api/v1/me/profile"


def register(client, username, profile):
    return client.post(
        AUTH + "/register",
        json={"username": username, "password": "rahasia123", "profile": profile},
    )


def login(client, username):
    r = client.post(AUTH + "/login", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 200


def count_users(username):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM users WHERE username = :u"), {"u": username}
        ).scalar()


def code(r):
    return r.status_code, r.json()["detail"]


def test_duplicate_email_is_409_even_with_different_case(client):
    first = make_profile()
    assert register(client, "budi", first).status_code == 201
    r = register(client, "siti", make_profile(email=first["email"].upper()))
    assert code(r) == (409, "EMAIL_TAKEN")


def test_duplicate_nik_is_409(client):
    first = make_profile()
    assert register(client, "budi", first).status_code == 201
    r = register(client, "siti", make_profile(nik=first["nik"]))
    assert code(r) == (409, "NIK_TAKEN")


def test_put_profile_conflicts_use_the_right_code(client):
    first = make_profile()
    assert register(client, "budi", first).status_code == 201
    assert register(client, "siti", make_profile()).status_code == 201
    login(client, "siti")
    assert code(client.put(ME, json=make_profile(email=first["email"]))) == (409, "EMAIL_TAKEN")
    assert code(client.put(ME, json=make_profile(nik=first["nik"]))) == (409, "NIK_TAKEN")


def test_put_profile_keeps_own_email_and_nik(client):
    mine = make_profile()
    assert register(client, "budi", mine).status_code == 201
    login(client, "budi")
    body = make_profile(email=mine["email"], nik=mine["nik"], phone="+628111111111")
    assert client.put(ME, json=body).status_code == 200
    assert client.get(ME).json()["phone"] == "+628111111111"


def test_rejected_registration_leaves_no_user(client):
    first = make_profile()
    assert register(client, "budi", first).status_code == 201
    assert register(client, "siti", make_profile(email=first["email"])).status_code == 409
    unknown_skill = make_profile(skill_ids=[str(uuid.uuid4())])
    assert register(client, "tono", unknown_skill).status_code == 422
    assert count_users("siti") == 0
    assert count_users("tono") == 0


def test_failure_after_the_user_insert_rolls_back(client, monkeypatch):
    def boom(db, user, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(profiles, "create_applicant", boom)
    with pytest.raises(RuntimeError):
        register(client, "budi", make_profile())
    assert count_users("budi") == 0


def test_unique_race_is_mapped_by_constraint_name(client, monkeypatch):
    first = make_profile()
    assert register(client, "budi", first).status_code == 201
    # With the early checks off, the database itself raises the unique violation.
    monkeypatch.setattr(profiles, "check_unique", lambda *args, **kwargs: None)
    r = register(client, "siti", make_profile(email=first["email"]))
    assert code(r) == (409, "EMAIL_TAKEN")
    r = register(client, "tono", make_profile(nik=first["nik"]))
    assert code(r) == (409, "NIK_TAKEN")
    assert count_users("siti") == 0
    assert count_users("tono") == 0


def test_profile_tables_have_no_plain_personal_columns(client):
    names = set()
    for table in ("applicant_profiles", "alumni_profiles"):
        names |= {c["name"] for c in inspect(engine).get_columns(table)}
    assert not names & {"full_name", "email", "phone", "nik", "address", "birth_date"}


def test_blind_indexes_are_stored(client):
    p = make_profile()
    assert register(client, "budi", p).status_code == 201
    with engine.connect() as conn:
        email_index = conn.execute(
            text("SELECT email_blind_index FROM users WHERE username = 'budi'")
        ).scalar()
        nik_index = conn.execute(text("SELECT nik_blind_index FROM applicant_profiles")).scalar()
    assert bytes(email_index) == blind_index.compute("email", p["email"])
    assert bytes(nik_index) == blind_index.compute("nik", p["nik"])