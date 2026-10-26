"""Per-application consent records (application_consents): grant, revoke and check a scope."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationConsent

SCOPES = ("profile", "cv", "video", "identity")

# Stored as an integer in application_consents.version; exposed as "v2" in the API.
VERSION = 2
VERSION_LABEL = "v2"

TEXTS = {
    "profile": "Allow the job owner to see my basic profile (name, email, class year, skills).",
    "cv": "Allow the job owner to open my CV.",
    "video": "Allow the job owner to open my introduction video.",
    "identity": (
        "Allow the job owner to view my identity data "
        "(NIK, address, birth date, ID card) after I am accepted, for 28 days."
    ),
}


def version_label(version: int) -> str:
    return "v%d" % version


def texts_view() -> dict:
    return {"version": VERSION_LABEL, "scopes": dict(TEXTS)}


def grant(db: Session, application_id: uuid.UUID, scopes: list[str]) -> None:
    """Record consent for each scope at the current text version.

    Called only when an application is created. There is no way to grant again
    later. Flushes only; the caller commits.
    """
    for scope in scopes:
        db.add(
            ApplicationConsent(
                application_id=application_id, scope=scope, version=VERSION
            )
        )
    db.flush()


def revoke(db: Session, application_id: uuid.UUID, scopes: list[str]) -> list[str]:
    """Set revoked_at on still-active consents and return the scopes just revoked.

    Already revoked consents are left untouched (idempotent, permanent). Scopes that
    were never granted have no row, so they are ignored. Flushes only.
    """
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(ApplicationConsent).where(
            ApplicationConsent.application_id == application_id,
            ApplicationConsent.scope.in_(scopes),
            ApplicationConsent.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        row.revoked_at = now
    db.flush()
    return [row.scope for row in rows]


def is_active(db: Session, application_id: uuid.UUID, scope: str) -> bool:
    """True when the consent was granted and has not been revoked."""
    row = db.scalar(
        select(ApplicationConsent).where(
            ApplicationConsent.application_id == application_id,
            ApplicationConsent.scope == scope,
        )
    )
    return row is not None and row.granted_at is not None and row.revoked_at is None


def views_of(db: Session, application_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(
        select(ApplicationConsent).where(
            ApplicationConsent.application_id == application_id
        )
    ).all()
    rows = sorted(
        rows,
        key=lambda r: SCOPES.index(r.scope) if r.scope in SCOPES else len(SCOPES),
    )
    return [
        {
            "scope": r.scope,
            "version": version_label(r.version),
            "granted_at": r.granted_at.isoformat(),
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        }
        for r in rows
    ]


def active_scopes(db: Session, application_ids) -> dict[uuid.UUID, set[str]]:
    """Scopes with an active consent (granted, not revoked) for each application id."""
    out = {i: set() for i in application_ids}
    if not out:
        return out
    rows = db.execute(
        select(ApplicationConsent.application_id, ApplicationConsent.scope).where(
            ApplicationConsent.application_id.in_(list(out)),
            ApplicationConsent.granted_at.is_not(None),
            ApplicationConsent.revoked_at.is_(None),
        )
    )
    for application_id, scope in rows:
        out[application_id].add(scope)
    return out