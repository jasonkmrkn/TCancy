"""keamanan tahap 2a: tabel refresh_tokens

Revision ID: raynald_02_refresh_tokens
Revises: raynald_01_password_hash
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "raynald_02_refresh_tokens"
down_revision = "raynald_01_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", uuid_pk, nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")