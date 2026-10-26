from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import csrf, tokens

from app.db import get_db
from app.ratelimit import RateLimitUnavailable
from app.routers import account as account_router
from app.routers import admin as admin_router
from app.routers import admin_audit as admin_audit_router
from app.routers import admin_benchmarks as admin_benchmarks_router
from app.routers import analysis as analysis_router
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

app = FastAPI(title="TCancy", lifespan=lifespan, dependencies=[Depends(csrf.verify_csrf)])
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
app.include_router(admin_audit_router.router)
app.include_router(analysis_router.router)
app.include_router(admin_benchmarks_router.router)

# Middleware slots (nothing installed yet). Starlette runs the LAST added
# middleware first (outermost), so add them in this order, top to bottom:
#   1. body-size limit   - reject oversized requests before anything reads them
#   2. CSRF              - check state-changing requests early
#   3. security headers  - must wrap every response, including errors
#   4. CORS              - add last so it is outermost and answers preflight first
# app.add_middleware(BodySizeLimitMiddleware)
# app.add_middleware(CSRFMiddleware)
# app.add_middleware(SecurityHeadersMiddleware)
# app.add_middleware(CORSMiddleware, ...)


@app.exception_handler(RateLimitUnavailable)
def rate_limit_unavailable_handler(_, __):
    return JSONResponse(status_code=503, content={"detail": "RATE_LIMIT_UNAVAILABLE"})


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
