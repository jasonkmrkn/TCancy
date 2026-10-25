from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import tokens

from app.db import get_db
from app.routers import account as account_router
from app.routers import admin as admin_router
from app.routers import applications as applications_router
from app.routers import auth as auth_router
from app.routers import dashboard as dashboard_router
from app.routers import documents as documents_router
from app.routers import jobs as jobs_router
from app.routers import owner as owner_router
from app.routers import profile as profile_router
from app.routers import testimonials as testimonials_router

@asynccontextmanager
async def lifespan(_: FastAPI):
    tokens.check_secret()
    yield

app = FastAPI(title="TCancy", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(profile_router.router)
app.include_router(account_router.router)
app.include_router(documents_router.router)
app.include_router(jobs_router.router)
app.include_router(applications_router.router)
app.include_router(owner_router.router)
app.include_router(admin_router.router)
app.include_router(testimonials_router.router)
app.include_router(dashboard_router.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready"}
