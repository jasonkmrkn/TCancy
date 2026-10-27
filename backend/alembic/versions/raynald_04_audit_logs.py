"""keamanan tahap 6: tabel audit_logs, append-only lewat trigger

Revision ID: raynald_04_audit_logs
Revises: raynald_03_drop_sessions
"""
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "raynald_04_audit_logs"
down_revision = "raynald_03_drop_sessions"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


APPEND_ONLY_SQL = (
    """CREATE OR REPLACE FUNCTION audit_logs_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only, UPDATE and DELETE are not allowed'
        USING ERRCODE = 'restrict_violation';
END;
$$""",
    """CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_reject_change()""",
    "ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER audit_logs_append_only",
)


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "audit_logs",
        sa.Column("id", uuid_type, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_id", uuid_type),
        sa.Column("actor_role", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text()),
        sa.Column("target_id", uuid_type),
        sa.Column("ip", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_actor_id_created_at", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_logs_target_id_created_at", "audit_logs", ["target_id", "created_at"])
    op.create_index(
        "ix_audit_logs_created_at_id", "audit_logs", [sa.text("created_at DESC"), sa.text("id DESC")]
    )
    for statement in APPEND_ONLY_SQL:
        op.execute(statement)


def downgrade() -> None:
    log.warning("downgrade drops audit_logs: every audit entry is lost")
    op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION audit_logs_reject_change()")
    op.drop_index("ix_audit_logs_created_at_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_id_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")