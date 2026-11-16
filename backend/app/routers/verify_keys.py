"""Admin public keys for alumni verification (owner: Axel).

Endpoints to be filled in:
  POST /admin/keys   register the admin's RSA-3072 public key (SPKI, from WebCrypto)
  GET  /admin/keys   read the admin's current key and its fingerprint

The private key never leaves the admin's browser; the server only stores the public key.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["verify-keys"])
