"""Removal of verification proofs after a decision or after the request expires (owner: Raynald).

To be filled in:
  - after the admin approves or rejects: delete the proof, the package and the wrapped K
  - after config.PROOF_REQUEST_TTL_DAYS days: do the same and mark the request as expired
  - delete the encrypted files from storage together with their database rows
"""
