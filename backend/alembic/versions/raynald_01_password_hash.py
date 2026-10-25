"""keamanan tahap 1: users.password (plaintext) -> users.password_hash (argon2id)

Revision ID: password_hash
Revises: 0008
"""
import logging

from alembic import op
import sqlalchemy as sa
from argon2 import PasswordHasher, profiles

revision = "raynald_01_password_hash"
down_revision = "0008"
branch_labels = ("raynald",)
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.alter_column("users", "password", new_column_name="password_hash")
    hasher = PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, password_hash FROM users")).all()
    for user_id, plaintext in rows:
        if plaintext.startswith("$argon2"):
            continue
        conn.execute(
            sa.text("UPDATE users SET password_hash = :h WHERE id = :id"),
            {"h": hasher.hash(plaintext), "id": user_id},
        )


def downgrade() -> None:
    log.warning(
        "downgrade keeps Argon2 hashes in users.password; old code cannot verify them, "
        "all passwords must be reset"
    )
    op.alter_column("users", "password_hash", new_column_name="password")