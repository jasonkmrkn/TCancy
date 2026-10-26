"""Access policy: what a job owner may see of an application.

Pure functions only: no database, no I/O. The caller passes the application status,
the scopes the applicant has consented to and not revoked, and the caller's role.
"""
from dataclasses import dataclass

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