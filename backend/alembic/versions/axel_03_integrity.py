"""integrity: HMAC tags per document chunk (integrity_tags) and per field (encrypted_fields.tag)

Revision ID: axel_03_integrity
Revises: axel_02_document_copies
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "axel_03_integrity"
down_revision = "axel_02_document_copies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "integrity_tags",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "document_copy_id", uuid_pk,
            sa.ForeignKey("document_copies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("tag", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_copy_id", "chunk_index", name="uq_integrity_tags_copy_chunk"),
    )
    op.add_column("encrypted_fields", sa.Column("tag", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("encrypted_fields", "tag")
    op.drop_table("integrity_tags")
