from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import account, audit, auth, limits
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["account"])


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str


@router.delete("/me/account")
def delete_my_account(
    body: DeleteAccountIn,
    request: Request,
    response: Response,
    user: User = Depends(require_role("applicant", "alumni", allow_pending=True)),
    db: Session = Depends(get_db),
):
    limits.delete_account(request, user.id)
    if not account.password_matches(user, body.password):
        raise HTTPException(status_code=403, detail="INVALID_PASSWORD")
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action="account.delete",
        target_type="user", target_id=user.id, **audit.client(request),
    )
    account.delete_account(db, user)
    auth.clear_auth_cookies(response)
    return {"ok": True}
