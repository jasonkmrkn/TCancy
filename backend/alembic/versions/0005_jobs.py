"""tahap 9: tabel jobs dan job_skills

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "jobs",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("work_mode", sa.Text(), nullable=False),
        sa.Column("location", sa.Text()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", sa.Text()),
        sa.Column("deadline", sa.Date()),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("ix_jobs_created_at_id", "jobs", ["created_at", "id"])
    op.create_table(
        "job_skills",
        sa.Column("job_id", uuid_pk, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", uuid_pk, sa.ForeignKey("skills.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("job_skills")
    op.drop_index("ix_jobs_created_at_id", table_name="jobs")
    op.drop_index("ix_jobs_owner_id", table_name="jobs")
    op.drop_table("jobs")
