from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import account, auth
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
    response: Response,
    user: User = Depends(require_role("applicant", "alumni", allow_pending=True)),
    db: Session = Depends(get_db),
):
    if not account.password_matches(user, body.password):
        raise HTTPException(status_code=403, detail="INVALID_PASSWORD")
    account.delete_account(db, user)
    auth.clear_auth_cookies(response)
    return {"ok": True}
