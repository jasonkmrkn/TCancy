"""drop plain personal-data columns from the profile tables

Revision ID: jason_02_drop_plain_profile
Revises: jason_01_blind_index_columns
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "jason_02_drop_plain_profile"
down_revision = "jason_01_blind_index_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Personal data now lives in encrypted_fields; there is no data migration (test data).
    op.drop_column("applicant_profiles", "full_name")
    op.drop_column("applicant_profiles", "email")
    op.drop_column("applicant_profiles", "phone")
    op.drop_column("applicant_profiles", "nik")
    op.drop_column("applicant_profiles", "address")
    op.drop_column("applicant_profiles", "birth_date")
    op.drop_column("alumni_profiles", "full_name")


def downgrade() -> None:
    # The values are not copied back: the restored columns are empty and nullable.
    op.add_column("alumni_profiles", sa.Column("full_name", sa.Text(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("nik", sa.Text(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("applicant_profiles", sa.Column("full_name", sa.Text(), nullable=True))