from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import dashboard, matching
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/me/matches")
def my_matches(
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    return {"items": matching.matches_for(db, user, limit)}


@router.get("/me/dashboard")
def my_dashboard(user: User = Depends(require_role("applicant")), db: Session = Depends(get_db)):
    return dashboard.applicant_dashboard(db, user)


@router.get("/owner/dashboard")
def owner_dashboard(
    user: User = Depends(require_role("alumni", "admin")), db: Session = Depends(get_db)
):
    return dashboard.owner_dashboard(db, user)
