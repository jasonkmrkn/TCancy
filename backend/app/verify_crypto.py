"""Server-side crypto for alumni verification proofs (owner: Axel).

To be filled in, using pycryptodome only:
  - derive the KEK with HKDF-SHA256 from the root key config.PROOF_KEKS[version]
  - encrypt the proof with a random key K (AES-256-GCM), one package made of
    config.PROOF_CHUNK_SIZE chunks
  - wrap K for the admin with RSA-OAEP (SHA-256) using the admin's public key (SPKI);
    the result is the access code the alumni sends to the admin
  - wrap K with the KEK for the server's own copy (proof_grants.k_wrapped, kek_version)

No endpoints here; routers call into this module.
"""
