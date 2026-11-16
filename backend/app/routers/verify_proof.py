"""Alumni verification proof upload (owner: Axel).

Endpoints to be filled in:
  POST   /me/verification-proof   upload the proof (PDF/JPG/PNG, at most config.PROOF_MAX_BYTES)
  GET    /me/verification-proof   metadata of the stored proof
  DELETE /me/verification-proof   delete the stored proof

File type checks and file storage come from app.filetype and app.storage (owner: Raynald).
The body limit for the upload is set in app.main (BodySizeLimitMiddleware).
Approve and reject stay in routers/admin.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["verify-proof"])
