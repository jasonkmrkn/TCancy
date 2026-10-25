"""tahap 12: kolom verifikasi alumni

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.add_column("alumni_profiles", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "alumni_profiles",
        sa.Column("verified_by", uuid_pk, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.add_column("alumni_profiles", sa.Column("rejected_at", sa.DateTime(timezone=True)))
    op.add_column("alumni_profiles", sa.Column("rejection_reason", sa.Text()))
    # Alumni yang sudah aktif sebelum tahap ini dianggap sudah disetujui.
    op.execute(
        "UPDATE alumni_profiles SET verified_at = now() "
        "FROM users WHERE users.id = alumni_profiles.user_id AND users.status = 'active'"
    )


def downgrade() -> None:
    op.drop_column("alumni_profiles", "rejection_reason")
    op.drop_column("alumni_profiles", "rejected_at")
    op.drop_column("alumni_profiles", "verified_by")
    op.drop_column("alumni_profiles", "verified_at")
