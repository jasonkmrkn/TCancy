"""
Schema changes for verification system.

Revision ID: verify_01_schema
Revises: verify_00_merge_heads
Create Date: 2026-11-16
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "verify_01_schema"
down_revision = "verify_00_merge_heads"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

REQUEST_STATUSES = ("pending", "granted", "closed", "expired")


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)

    op.create_table(
        "user_public_keys",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("public_key_spki", sa.LargeBinary(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_user_public_keys_active", "user_public_keys", ["user_id"],
        unique=True, postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "verification_proofs",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("alumni_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("ext", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "verification_proof_copies",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("proof_id", uuid_pk, sa.ForeignKey("verification_proofs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary()),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default=sa.text("4194304")),
        sa.Column("ciphertext_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("proof_id", "algorithm", name="uq_verification_proof_copies_proof_algorithm"),
    )

    op.create_table(
        "verification_requests",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("alumni_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.Text()),
        sa.CheckConstraint(
            "status IN (%s)" % ", ".join(f"'{s}'" for s in REQUEST_STATUSES),
            name="ck_verification_requests_status",
        ),
    )
    op.create_index("ix_verification_requests_alumni_id", "verification_requests", ["alumni_id"])
    op.create_index("ix_verification_requests_admin_id", "verification_requests", ["admin_id"])
    op.create_index(
        "uq_verification_requests_open", "verification_requests", ["alumni_id", "admin_id"],
        unique=True, postgresql_where=sa.text("status IN ('pending', 'granted')"),
    )

    op.create_table(
        "proof_grants",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "request_id", uuid_pk,
            sa.ForeignKey("verification_requests.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("recipient_key_id", uuid_pk, sa.ForeignKey("user_public_keys.id"), nullable=False),
        sa.Column("k_wrapped", sa.LargeBinary(), nullable=False),
        sa.Column("kek_salt", sa.LargeBinary(), nullable=False),
        sa.Column("kek_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("kek_version", sa.Integer(), nullable=False),
        sa.Column("pkg_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("pkg_storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("pkg_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
    )

    op.add_column("alumni_profiles", sa.Column("proof_sha256", sa.Text()))


def downgrade() -> None:
    log.warning(
        "downgrade drops the verification tables: public keys, proofs, requests and grants are lost "
        "(encrypted files in UPLOAD_DIR stay on disk)"
    )
    op.drop_column("alumni_profiles", "proof_sha256")
    op.drop_table("proof_grants")
    op.drop_index("uq_verification_requests_open", table_name="verification_requests")
    op.drop_index("ix_verification_requests_admin_id", table_name="verification_requests")
    op.drop_index("ix_verification_requests_alumni_id", table_name="verification_requests")
    op.drop_table("verification_requests")
    op.drop_table("verification_proof_copies")
    op.drop_table("verification_proofs")
    op.drop_index("uq_user_public_keys_active", table_name="user_public_keys")
    op.drop_table("user_public_keys")