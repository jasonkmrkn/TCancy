"""tahap 13: tabel testimonials

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "testimonials",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", uuid_pk, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("show_name", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_first_name", sa.Text()),
        sa.Column("display_company", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("moderated_by", uuid_pk, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("moderated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("application_id", name="uq_testimonials_application"),
    )
    op.create_index("ix_testimonials_author_id", "testimonials", ["author_id"])
    op.create_index("ix_testimonials_status", "testimonials", ["status"])


def downgrade() -> None:
    op.drop_index("ix_testimonials_status", table_name="testimonials")
    op.drop_index("ix_testimonials_author_id", table_name="testimonials")
    op.drop_table("testimonials")
