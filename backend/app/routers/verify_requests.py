"""Proof requests and grants between admin and alumni (owner: Jason).

Endpoints to be filled in:
  POST /admin/alumni/{id}/proof-request           admin asks an alumni for the proof
  GET  /me/verification-requests                  alumni lists the requests addressed to them
  POST /me/verification-requests/{id}/grant       alumni agrees; the server builds the package
  GET  /admin/proof-grants/{id}                   grant metadata for the admin
  GET  /admin/proof-grants/{id}/package           download the encrypted package

At most one open request (pending or granted) per alumni-admin pair is enforced by the
partial unique index uq_verification_requests_open; answer 409 REQUEST_EXISTS on conflict.
Approve and reject stay in routers/admin.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["verify-requests"])
