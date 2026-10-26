"""Access policy: what a job owner may see of an application.

Pure functions only: no database, no I/O. The caller passes the application status,
the scopes the applicant has consented to and not revoked, and the caller's role.
"""
from dataclasses import dataclass
from datetime import datetime

OWNER_ROLES = ("alumni", "admin")

# The phone number comes with the applicant object, so it also needs the profile
# consent. It appears only from the shortlist stage on. The rule looks at the current
# status alone: rejected and withdrawn do not show it, even after an earlier shortlist.
PHONE_STATUSES = ("shortlisted", "accepted")


@dataclass(frozen=True)
class Visibility:
    profile: bool = False
    phone: bool = False
    cv: bool = False
    video: bool = False


def decide(status: str, active_scopes, caller_role: str) -> Visibility:
    """What the caller may see. Default is nothing."""
    if caller_role not in OWNER_ROLES:
        return Visibility()
    scopes = frozenset(active_scopes)
    profile = "profile" in scopes
    return Visibility(
        profile=profile,
        phone=profile and status in PHONE_STATUSES,
        cv="cv" in scopes,
        video="video" in scopes,
    )


IDENTITY_LOCKED = "locked"
IDENTITY_EXPIRED = "expired"
IDENTITY_AVAILABLE = "available"


def identity_state(
    status: str, active_scopes, expires_at: datetime | None, now: datetime, caller_role: str
) -> str:
    """Whether the job owner may open the applicant's identity data.

    Open only when the application is accepted, the identity consent is active and the
    access window (set when the application was first accepted) has not passed. A window
    that was never recorded keeps the data locked. `now` comes from the caller.
    """
    if caller_role not in OWNER_ROLES:
        return IDENTITY_LOCKED
    if status != "accepted" or "identity" not in frozenset(active_scopes):
        return IDENTITY_LOCKED
    if expires_at is None:
        return IDENTITY_LOCKED
    if now > expires_at:
        return IDENTITY_EXPIRED
    return IDENTITY_AVAILABLE


def shown_expiry(state: str, expires_at: datetime | None) -> datetime | None:
    """The expiry date is shown only when the data is not locked."""
    return None if state == IDENTITY_LOCKED else expires_at