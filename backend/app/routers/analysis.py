from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app import analysis, audit, benchmarks
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["analysis"])


class BenchmarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeats: StrictInt = Field(default=5, ge=1, le=10)


def _audit(db: Session, request: Request, user: User, action: str, doc_id: str, **counts: int) -> None:
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action=action,
        target_type="document", target_id=doc_id,
        details=audit.details(**counts),
        **audit.client(request),
    )
    db.commit()


@router.get("/me/documents/{doc_id}/ciphertext")
def ciphertext(
    doc_id: str,
    request: Request,
    preview: int = Query(default=48, ge=8, le=128, alias="bytes"),
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    view = analysis.ciphertext_view(db, user, doc_id, preview)
    doc = view["document"]
    _audit(db, request, user, "document.ciphertext_view", doc["id"],
           copies=len(view["copies"]), size=doc["size"], bytes=view["preview_bytes"])
    return view


@router.post("/me/documents/{doc_id}/benchmark")
def benchmark(
    doc_id: str,
    request: Request,
    body: BenchmarkIn | None = None,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    repeats = (body or BenchmarkIn()).repeats
    result = benchmarks.run_document(db, user, doc_id, repeats)
    doc = result["document"]
    _audit(db, request, user, "document.benchmark", doc["id"],
           repeats=repeats, copies=len(result["results"]), size=doc["size"])
    return result
