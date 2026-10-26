import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import blind_index, vault
from app.models import AlumniProfile, ApplicantProfile, ApplicantSkill, Skill, User
from app.schemas import AlumniProfileIn, ApplicantProfileIn

# Personal fields live in the vault (encrypted_fields). The profile rows keep only
# non-personal columns and the blind indexes used for uniqueness.


def conflict_code(exc: IntegrityError) -> str | None:
    """Map a unique-constraint violation to its API error code, or None for any other error.

    Only the constraint name is read, never the values, so no personal data reaches an error.
    """
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None) or ""
    if "email_blind_index" in name:
        return "EMAIL_TAKEN"
    if "nik_blind_index" in name:
        return "NIK_TAKEN"
    if "username" in name:
        return "USERNAME_TAKEN"
    return None


def _flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        code = conflict_code(exc)
        if code is None:
            raise
        raise HTTPException(status_code=409, detail=code) from None


def check_unique(db: Session, data: ApplicantProfileIn, user_id: uuid.UUID | None = None) -> None:
    """409 when the email or NIK already belongs to another applicant (compared by blind index)."""
    email_query = select(User.id).where(
        User.email_blind_index == blind_index.compute("email", data.email)
    )
    nik_query = select(ApplicantProfile.user_id).where(
        ApplicantProfile.nik_blind_index == blind_index.compute("nik", data.nik)
    )
    if user_id is not None:
        email_query = email_query.where(User.id != user_id)
        nik_query = nik_query.where(ApplicantProfile.user_id != user_id)
    if db.scalar(email_query) is not None:
        raise HTTPException(status_code=409, detail="EMAIL_TAKEN")
    if db.scalar(nik_query) is not None:
        raise HTTPException(status_code=409, detail="NIK_TAKEN")


def check_skills(db: Session, skill_ids: list[uuid.UUID]) -> None:
    found = set(db.scalars(select(Skill.id).where(Skill.id.in_(skill_ids))))
    unknown = [str(s) for s in skill_ids if s not in found]
    if unknown:
        raise HTTPException(status_code=422, detail="unknown skill: " + ", ".join(unknown))


def _set_skills(db: Session, user_id: uuid.UUID, skill_ids: list[uuid.UUID]) -> None:
    db.execute(delete(ApplicantSkill).where(ApplicantSkill.user_id == user_id))
    db.add_all([ApplicantSkill(user_id=user_id, skill_id=s) for s in skill_ids])


def _save_applicant(
    db: Session, user: User, profile: ApplicantProfile, data: ApplicantProfileIn
) -> None:
    user.email_blind_index = blind_index.compute("email", data.email)
    profile.nik_blind_index = blind_index.compute("nik", data.nik)
    profile.angkatan = data.angkatan
    profile.preferred_type = data.preferred_type
    profile.preferred_location = data.preferred_location
    db.add(profile)
    _flush(db)
    personal = {
        "full_name": data.full_name,
        "email": data.email,
        "phone": data.phone,
        "nik": data.nik,
        "address": data.address,
        "birth_date": data.birth_date.isoformat(),
    }
    for field, value in personal.items():
        vault.store_field(db, user.id, field, value)
    _set_skills(db, user.id, data.skill_ids)
    db.flush()


def applicant_profile_out(db: Session, user: User) -> dict:
    profile = db.get(ApplicantProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    skills = db.execute(
        select(Skill.id, Skill.name)
        .join(ApplicantSkill, ApplicantSkill.skill_id == Skill.id)
        .where(ApplicantSkill.user_id == user.id)
        .order_by(Skill.name)
    ).all()
    return {
        "role": "applicant",
        "full_name": vault.load_field(db, user.id, "full_name"),
        "email": vault.load_field(db, user.id, "email"),
        "phone": vault.load_field(db, user.id, "phone"),
        "nik": vault.load_field(db, user.id, "nik"),
        "address": vault.load_field(db, user.id, "address"),
        "birth_date": vault.load_field(db, user.id, "birth_date"),
        "angkatan": profile.angkatan,
        "skills": [{"id": str(i), "name": n} for i, n in skills],
        "preferred_type": profile.preferred_type,
        "preferred_location": profile.preferred_location,
    }


def get_alumni_profile(db: Session, user_id: uuid.UUID) -> AlumniProfile:
    profile = db.get(AlumniProfile, user_id)
    if profile is None:
        profile = AlumniProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


def alumni_profile_complete(profile: AlumniProfile, full_name: str | None) -> bool:
    return bool(full_name and profile.company and profile.angkatan)


def replace_alumni_profile(db: Session, user: User, data: AlumniProfileIn) -> None:
    profile = get_alumni_profile(db, user.id)
    # The vault has no delete, so a cleared name is stored as "" and read back as None.
    vault.store_field(db, user.id, "full_name", data.full_name or "")
    profile.company = data.company
    profile.angkatan = data.angkatan
    if profile.rejected_at is not None:
        # Editing after a rejection counts as applying again.
        profile.rejected_at = None
        profile.rejection_reason = None


def alumni_verification(user: User, profile: AlumniProfile) -> dict:
    if profile.verified_at is not None or user.status == "active":
        return {"state": "approved", "reason": None}
    if profile.rejected_at is not None:
        return {"state": "rejected", "reason": profile.rejection_reason}
    return {"state": "pending", "reason": None}


def alumni_profile_out(db: Session, user: User) -> dict:
    profile = get_alumni_profile(db, user.id)
    full_name = display_name(db, user.id)
    return {
        "role": "alumni",
        "full_name": full_name,
        "company": profile.company,
        "angkatan": profile.angkatan,
        "profile_complete": alumni_profile_complete(profile, full_name),
        "verification": alumni_verification(user, profile),
    }


def create_applicant(db: Session, user: User, data: ApplicantProfileIn) -> None:
    """Frozen interface: create the applicant profile and its skills at registration.

    422 for an unknown skill, 409 EMAIL_TAKEN / NIK_TAKEN. The caller commits.
    """
    check_skills(db, data.skill_ids)
    check_unique(db, data, user.id)
    _save_applicant(db, user, ApplicantProfile(user_id=user.id), data)


def create_alumni(db: Session, user: User, data: AlumniProfileIn | None) -> None:
    """Frozen interface: create the alumni profile row at registration.

    `data` may be None, as registration sends no profile data today. The caller commits.
    """
    get_alumni_profile(db, user.id)
    if data is not None:
        replace_alumni_profile(db, user, data)


def read(db: Session, user: User) -> dict:
    """Frozen interface: the body of GET /me/profile for the user's role."""
    if user.role == "alumni":
        return alumni_profile_out(db, user)
    return applicant_profile_out(db, user)


def update(db: Session, user: User, data: ApplicantProfileIn | AlumniProfileIn) -> dict:
    """Frozen interface: PUT /me/profile. `data` is the body already parsed for the user's role.

    Same errors as create_applicant for applicants. The caller commits.
    """
    if user.role == "alumni":
        replace_alumni_profile(db, user, data)
        return alumni_profile_out(db, user)
    check_skills(db, data.skill_ids)
    check_unique(db, data, user.id)
    profile = db.get(ApplicantProfile, user.id) or ApplicantProfile(user_id=user.id)
    _save_applicant(db, user, profile, data)
    return applicant_profile_out(db, user)


def display_name(db: Session, user_id: uuid.UUID) -> str | None:
    """Frozen interface: the user's full name, for testimonials and admin lists."""
    return vault.load_field(db, user_id, "full_name") or None