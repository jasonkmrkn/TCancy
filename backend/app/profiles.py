import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AlumniProfile, ApplicantProfile, ApplicantSkill, Skill, User
from app.schemas import AlumniProfileIn, ApplicantProfileIn


def check_unique(db: Session, data: ApplicantProfileIn, user_id: uuid.UUID | None = None) -> None:
    """409 when the email or NIK already belongs to another applicant."""
    for column, code, value in (
        (ApplicantProfile.email, "EMAIL_TAKEN", data.email),
        (ApplicantProfile.nik, "NIK_TAKEN", data.nik),
    ):
        query = select(ApplicantProfile.user_id).where(column == value)
        if user_id is not None:
            query = query.where(ApplicantProfile.user_id != user_id)
        if db.scalar(query) is not None:
            raise HTTPException(status_code=409, detail=code)


def check_skills(db: Session, skill_ids: list[uuid.UUID]) -> None:
    found = set(db.scalars(select(Skill.id).where(Skill.id.in_(skill_ids))))
    unknown = [str(s) for s in skill_ids if s not in found]
    if unknown:
        raise HTTPException(status_code=422, detail="unknown skill: " + ", ".join(unknown))


def _apply(profile: ApplicantProfile, data: ApplicantProfileIn) -> None:
    profile.full_name = data.full_name
    profile.email = data.email
    profile.phone = data.phone
    profile.nik = data.nik
    profile.address = data.address
    profile.birth_date = data.birth_date
    profile.angkatan = data.angkatan
    profile.preferred_type = data.preferred_type
    profile.preferred_location = data.preferred_location


def _set_skills(db: Session, user_id: uuid.UUID, skill_ids: list[uuid.UUID]) -> None:
    db.execute(delete(ApplicantSkill).where(ApplicantSkill.user_id == user_id))
    db.add_all([ApplicantSkill(user_id=user_id, skill_id=s) for s in skill_ids])


def create_applicant_profile(db: Session, user_id: uuid.UUID, data: ApplicantProfileIn) -> None:
    profile = ApplicantProfile(user_id=user_id)
    _apply(profile, data)
    db.add(profile)
    db.flush()
    _set_skills(db, user_id, data.skill_ids)


def replace_applicant_profile(db: Session, user: User, data: ApplicantProfileIn) -> None:
    profile = db.get(ApplicantProfile, user.id)
    if profile is None:
        create_applicant_profile(db, user.id, data)
        return
    _apply(profile, data)
    db.flush()
    _set_skills(db, user.id, data.skill_ids)


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
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "nik": profile.nik,
        "address": profile.address,
        "birth_date": profile.birth_date.isoformat(),
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


def alumni_profile_complete(profile: AlumniProfile) -> bool:
    return bool(profile.full_name and profile.company and profile.angkatan)


def replace_alumni_profile(db: Session, user: User, data: AlumniProfileIn) -> None:
    profile = get_alumni_profile(db, user.id)
    profile.full_name = data.full_name
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
    return {
        "role": "alumni",
        "full_name": profile.full_name,
        "company": profile.company,
        "angkatan": profile.angkatan,
        "profile_complete": alumni_profile_complete(profile),
        "verification": alumni_verification(user, profile),
    }
