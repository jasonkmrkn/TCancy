"""document_copies: one encrypted file per algorithm; documents loses storage_key

Revision ID: axel_02_document_copies
Revises: axel_01_encrypted_fields
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "axel_02_document_copies"
down_revision = "axel_01_encrypted_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "document_copies",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", uuid_pk, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary()),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default=sa.text("4194304")),
        sa.Column("ciphertext_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "algorithm", name="uq_document_copies_document_algorithm"),
    )
    # Files now live in document_copies; the unique constraint goes with the column.
    op.drop_column("documents", "storage_key")


def downgrade() -> None:
    # The keys are not copied back: the restored column is empty and nullable.
    op.add_column("documents", sa.Column("storage_key", sa.Text(), nullable=True))
    op.create_unique_constraint("documents_storage_key_key", "documents", ["storage_key"])
    op.drop_table("document_copies")
