from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import config, csrf, tokens

from app.db import get_db
from app.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware, add_security_headers
from app.origin import OriginCheckMiddleware
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

MiB = 1024 * 1024
app.add_middleware(
    BodySizeLimitMiddleware,
    default_limit=1 * MiB,
    limits={("POST", "/api/v1/me/documents"): 51 * MiB},  # 50 MiB video + form overhead
)
app.add_middleware(OriginCheckMiddleware, allowed_origin=config.FRONTEND_ORIGIN)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", csrf.CSRF_HEADER],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(RateLimitUnavailable)
def rate_limit_unavailable_handler(_, __):
    return JSONResponse(status_code=503, content={"detail": "RATE_LIMIT_UNAVAILABLE"})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_, exc: RequestValidationError):
    # FastAPI's default 422 echoes the rejected input (`input`, `ctx`), which includes
    # passwords and NIK. Keep only what the front end uses: where (loc), what (msg), kind (type).
    errors = [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.exception_handler(Exception)
async def unhandled_error_handler(_, __):
    # Same body as Starlette's default 500. This response is built outside every middleware
    # of ours (ServerErrorMiddleware wraps them all), so it gets the headers by hand. The
    # exception is still re-raised afterwards, so the server logs the traceback as before.
    response = PlainTextResponse("Internal Server Error", status_code=500)
    add_security_headers(response)
    return response


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