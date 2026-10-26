"""One place for route handlers to write an audit entry.

The caller passes only names, counts and ids in details, never a personal value (name, email,
NIK, address, phone, password or token). The entry joins the caller's transaction and is
committed with it, like the audit calls in the documents router.
"""

from fastapi import Request
from sqlalchemy.orm import Session

from app import audit, clientip
from app.models import User


def log(
    db: Session,
    request: Request,
    user: User,
    action: str,
    target_type: str | None = None,
    target_id=None,
    details: dict | None = None,
) -> None:
    audit.record(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        ip=clientip.client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )
    db.commit()
