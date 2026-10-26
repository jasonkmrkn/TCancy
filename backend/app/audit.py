# STUB-RAYNALD
"""Audit log writer.

Interface-stub stage: record() does nothing. The real implementation inserts a row into
audit_logs and does not commit either; the caller commits with its own transaction.
"""


# STUB-RAYNALD
def record(db, *, actor_id, actor_role, action, target_type=None, target_id=None,
           ip=None, user_agent=None, details: dict | None = None) -> None:
    """Frozen interface: write one audit entry. The stub does nothing."""