"""tahap 10: tabel applications dan application_status_history

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "applications",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", uuid_pk, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("applicant_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("cover_note", sa.Text()),
        sa.Column("cv_document_id", uuid_pk),
        sa.Column("intro_video_document_id", uuid_pk),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["cv_document_id", "applicant_id"], ["documents.id", "documents.owner_id"],
            name="fk_applications_cv_document",
        ),
        sa.ForeignKeyConstraint(
            ["intro_video_document_id", "applicant_id"], ["documents.id", "documents.owner_id"],
            name="fk_applications_video_document",
        ),
        sa.UniqueConstraint("job_id", "applicant_id", name="uq_applications_job_applicant"),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_applicant_id", "applications", ["applicant_id"])
    op.create_table(
        "application_status_history",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", uuid_pk, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("changed_by", uuid_pk, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_application_status_history_application_id", "application_status_history", ["application_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_application_status_history_application_id", table_name="application_status_history")
    op.drop_table("application_status_history")
    op.drop_index("ix_applications_applicant_id", table_name="applications")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_table("applications")
