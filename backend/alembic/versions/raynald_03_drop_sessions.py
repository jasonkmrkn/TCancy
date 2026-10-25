"""keamanan tahap 2b: hapus tabel sessions (digantikan refresh_tokens)

Revision ID: raynald_03_drop_sessions
Revises: raynald_02_refresh_tokens
"""
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "raynald_03_drop_sessions"
down_revision = "raynald_02_refresh_tokens"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")


def downgrade() -> None:
    log.warning("downgrade recreates the sessions table empty; all logins are lost")
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])