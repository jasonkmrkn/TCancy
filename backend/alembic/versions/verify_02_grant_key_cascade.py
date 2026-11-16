"""assignment 2: proof_grants.recipient_key_id ikut terhapus bersama key admin

Deleting an admin account deletes their public keys (ON DELETE CASCADE from users) and their
requests (admin_id, CASCADE), and the requests take the grants with them. Both cascades start
from the same DELETE, but Postgres may check the plain foreign key from proof_grants to
user_public_keys before the grant is gone, so the delete failed with a foreign key violation.
A grant is useless without the key it is wrapped for, so it now goes with the key.

Revision ID: verify_02_grant_key_cascade
Revises: verify_01_schema
Create Date: 2026-11-16
"""
from alembic import op

revision = "verify_02_grant_key_cascade"
down_revision = "verify_01_schema"
branch_labels = None
depends_on = None

FK = "proof_grants_recipient_key_id_fkey"


def upgrade() -> None:
    op.drop_constraint(FK, "proof_grants", type_="foreignkey")
    op.create_foreign_key(
        FK, "proof_grants", "user_public_keys", ["recipient_key_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint(FK, "proof_grants", type_="foreignkey")
    op.create_foreign_key(FK, "proof_grants", "user_public_keys", ["recipient_key_id"], ["id"])
