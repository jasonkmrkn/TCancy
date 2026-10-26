"""crypto_benchmarks: timings of user and synthetic benchmark runs

Revision ID: axel_04_crypto_benchmarks
Revises: axel_03_integrity
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "axel_04_crypto_benchmarks"
down_revision = "axel_03_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "crypto_benchmarks",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", uuid_pk, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("crypto_ms", sa.Float(), nullable=False),
        sa.Column("integrity_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_ms", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("run_no", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("crypto_benchmarks")
