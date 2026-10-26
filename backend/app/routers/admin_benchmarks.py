from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app import audit, benchmarks, clientip
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["admin-benchmarks"])

Admin = require_role("admin")


class BenchmarkRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sizes: list[Annotated[StrictInt, Field(ge=1, le=4 * 1024 * 1024)]] = Field(
        default=[1024, 65536, 1048576], min_length=1, max_length=6
    )
    repeats: StrictInt = Field(default=3, ge=1, le=10)


@router.post("/admin/benchmarks/run")
def run(
    request: Request,
    body: BenchmarkRunIn | None = None,
    user: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    body = body or BenchmarkRunIn()
    result = benchmarks.run_synthetic(db, user, body.sizes, body.repeats)
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action="admin.benchmark_run",
        ip=clientip.client_ip(request), user_agent=request.headers.get("user-agent"),
        details={"run_no": result["run_no"], "samples": result["samples"], "total_bytes": result["total_bytes"]},
    )
    db.commit()
    return {"run_no": result["run_no"], "samples": result["samples"]}


@router.get("/admin/benchmarks")
def summary(
    source: Literal["user", "benchmark"] | None = None,
    user: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    return benchmarks.summary(db, source)
