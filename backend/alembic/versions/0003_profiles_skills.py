"""tahap 6: profil pelamar dan alumni, skills, applicant_skills

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SKILLS = ['Python', 'JavaScript', 'TypeScript', 'Java', 'C++', 'C#', 'Go', 'PHP', 'Ruby', 'Kotlin', 'Swift', 'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'React', 'Next.js', 'Vue.js', 'Angular', 'Node.js', 'Django', 'FastAPI', 'Flask', 'Laravel', 'Spring Boot', 'HTML', 'CSS', 'Tailwind CSS', 'Git', 'Docker', 'Linux', 'AWS', 'REST API', 'GraphQL', 'Machine Learning', 'Data Analysis', 'Flutter', 'Android', 'UI/UX Design', 'Networking']


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    uuid_pk = postgresql.UUID(as_uuid=True)
    op.create_table(
        "applicant_profiles",
        sa.Column("user_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("nik", sa.Text(), nullable=False, unique=True),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("angkatan", sa.SmallInteger(), nullable=False),
        sa.Column("preferred_type", sa.Text()),
        sa.Column("preferred_location", sa.Text()),
        *_timestamps(),
    )
    op.create_table(
        "alumni_profiles",
        sa.Column("user_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("full_name", sa.Text()),
        sa.Column("company", sa.Text()),
        sa.Column("angkatan", sa.SmallInteger()),
        *_timestamps(),
    )
    skills = op.create_table(
        "skills",
        sa.Column("id", uuid_pk, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "applicant_skills",
        sa.Column("user_id", uuid_pk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", uuid_pk, sa.ForeignKey("skills.id"), primary_key=True),
    )
    op.bulk_insert(skills, [{"name": n} for n in SKILLS])


def downgrade() -> None:
    op.drop_table("applicant_skills")
    op.drop_table("skills")
    op.drop_table("alumni_profiles")
    op.drop_table("applicant_profiles")
