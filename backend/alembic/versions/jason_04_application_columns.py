"""add applications.accepted_at and applications.identity_access_expires_at

Revision ID: jason_04_application_access_columns
Revises: jason_03_application_consents
"""
import sqlalchemy as sa
from alembic import op

revision = "jason_04_application_columns"
down_revision = "jason_03_application_consents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column(
            "identity_access_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("applications", "identity_access_expires_at")
    op.drop_column("applications", "accepted_at")