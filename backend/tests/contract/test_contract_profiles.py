"""Contract for app.profiles: create_applicant, create_alumni, read, update and display_name."""
import uuid

import pytest
from fastapi import HTTPException

from app import profiles
from app.schemas import AlumniProfileIn, ApplicantProfileIn
from helpers import make_profile

APPLICANT_KEYS = {
    "role", "full_name", "email", "phone", "nik", "address", "birth_date",
    "angkatan", "skills", "preferred_type", "preferred_location",
}


def _applicant(**over):
    return ApplicantProfileIn(**make_profile(**over))


def _alumni(full_name="Siti Rahma"):
    return AlumniProfileIn(full_name=full_name, company="Acme Corp", angkatan=2015)


def _changed(data, **over):
    return ApplicantProfileIn(**{**data.model_dump(mode="json"), **over})


def test_read_returns_the_applicant_profile_after_create(db, make_user):
    user = make_user()
    data = _applicant()
    profiles.create_applicant(db, user, data)
    db.commit()
    out = profiles.read(db, user)
    assert APPLICANT_KEYS <= set(out)
    assert out["role"] == "applicant"
    assert out["full_name"] == data.full_name
    assert out["email"] == data.email
    assert {s["id"] for s in out["skills"]} == {str(s) for s in data.skill_ids}
    assert all({"id", "name"} <= set(s) for s in out["skills"])


def test_read_returns_the_alumni_profile_after_create(db, make_user):
    user = make_user(role="alumni")
    profiles.create_alumni(db, user, _alumni())
    db.commit()
    out = profiles.read(db, user)
    assert out["role"] == "alumni"
    assert out["full_name"] == "Siti Rahma"
    assert "state" in out["verification"]


def test_update_returns_the_new_applicant_profile(db, make_user):
    user = make_user()
    data = _applicant()
    profiles.create_applicant(db, user, data)
    db.commit()
    out = profiles.update(db, user, _changed(data, full_name="Budi Baru"))
    db.commit()
    assert out["full_name"] == "Budi Baru"
    assert profiles.read(db, user)["full_name"] == "Budi Baru"


def test_update_returns_the_new_alumni_profile(db, make_user):
    user = make_user(role="alumni")
    profiles.create_alumni(db, user, _alumni())
    db.commit()
    out = profiles.update(db, user, _alumni("Nama Baru"))
    db.commit()
    assert out["role"] == "alumni"
    assert out["full_name"] == "Nama Baru"


def test_display_name_of_an_applicant_is_the_full_name(db, make_user):
    user = make_user()
    data = _applicant()
    profiles.create_applicant(db, user, data)
    db.commit()
    assert profiles.display_name(db, user.id) == data.full_name


def test_display_name_of_an_alumnus_is_the_full_name(db, make_user):
    user = make_user(role="alumni")
    profiles.create_alumni(db, user, _alumni("Siti Rahma"))
    db.commit()
    assert profiles.display_name(db, user.id) == "Siti Rahma"


def test_display_name_is_none_without_a_profile(db, make_user):
    assert profiles.display_name(db, make_user().id) is None
    assert profiles.display_name(db, uuid.uuid4()) is None


def test_create_applicant_rejects_a_taken_email(db, make_user):
    first = _applicant()
    profiles.create_applicant(db, make_user(), first)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        profiles.create_applicant(db, make_user(), _applicant(email=first.email))
    assert exc.value.status_code == 409
    assert exc.value.detail == "EMAIL_TAKEN"


def test_create_applicant_rejects_a_taken_nik(db, make_user):
    first = _applicant()
    profiles.create_applicant(db, make_user(), first)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        profiles.create_applicant(db, make_user(), _applicant(nik=first.nik))
    assert exc.value.status_code == 409
    assert exc.value.detail == "NIK_TAKEN"


def test_create_applicant_rejects_an_unknown_skill(db, make_user):
    with pytest.raises(HTTPException) as exc:
        profiles.create_applicant(db, make_user(), _applicant(skill_ids=[str(uuid.uuid4())]))
    assert exc.value.status_code == 422


def test_update_rejects_an_email_taken_by_someone_else(db, make_user):
    first = _applicant()
    profiles.create_applicant(db, make_user(), first)
    other_user = make_user()
    other = _applicant()
    profiles.create_applicant(db, other_user, other)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        profiles.update(db, other_user, _changed(other, email=first.email))
    assert exc.value.status_code == 409
    assert exc.value.detail == "EMAIL_TAKEN"