"""add users.email_blind_index and applicant_profiles.nik_blind_index

Revision ID: jason_01_blind_index_columns
Revises: jason_00_branch_root
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "jason_01_blind_index_columns"
down_revision = "jason_00_branch_root"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_blind_index", sa.LargeBinary(), nullable=True))
    op.create_unique_constraint("users_email_blind_index_key", "users", ["email_blind_index"])
    op.add_column(
        "applicant_profiles", sa.Column("nik_blind_index", sa.LargeBinary(), nullable=True)
    )
    op.create_unique_constraint(
        "applicant_profiles_nik_blind_index_key", "applicant_profiles", ["nik_blind_index"]
    )


def downgrade() -> None:
    op.drop_constraint("applicant_profiles_nik_blind_index_key", "applicant_profiles", type_="unique")
    op.drop_column("applicant_profiles", "nik_blind_index")
    op.drop_constraint("users_email_blind_index_key", "users", type_="unique")
    op.drop_column("users", "email_blind_index")