import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import jobs
from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, User

router = APIRouter(prefix="/api/v1", tags=["admin-audit"])

Admin = require_role("admin")


def _utc(value: datetime | None) -> datetime | None:
    """A time without a zone is taken as UTC, as the cursor does."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _item(row: AuditLog) -> dict:
    # user_agent is stored but not returned.
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat(),
        "action": row.action,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "actor_role": row.actor_role,
        "target_type": row.target_type,
        "target_id": str(row.target_id) if row.target_id else None,
        "ip": row.ip,
        "details": row.details,
    }


@router.get("/admin/audit-logs")
def list_audit_logs(
    action: str | None = Query(default=None, max_length=64),
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=200),
    _: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    """Newest first. `since` is included, `until` is not."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if target_id:
        query = query.where(AuditLog.target_id == target_id)
    if since:
        query = query.where(AuditLog.created_at >= _utc(since))
    if until:
        query = query.where(AuditLog.created_at < _utc(until))
    if cursor:
        created_at, ident = jobs.decode_cursor(cursor)
        query = query.where(
            or_(AuditLog.created_at < created_at, and_(AuditLog.created_at == created_at, AuditLog.id < ident))
        )
    rows = list(db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    next_cursor = jobs.encode_cursor(page[-1]) if len(rows) > limit else None
    return {"items": [_item(row) for row in page], "next_cursor": next_cursor}