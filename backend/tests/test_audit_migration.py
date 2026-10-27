import os
import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app import config
from app.db import engine

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REVISION = "raynald_04_audit_logs"
PREVIOUS = "raynald_03_drop_sessions"

TEST_URL = make_url(config.DATABASE_URL)
SCRATCH_NAME = TEST_URL.database + "_audit_migration"  # still ends in _test
SCRATCH_URL = TEST_URL.set(database=SCRATCH_NAME)


def alembic(*args):
    env = {**os.environ, "DATABASE_URL": SCRATCH_URL.render_as_string(hide_password=False)}
    done = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done


@pytest.fixture(scope="module")
def scratch():
    admin = create_engine(TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % SCRATCH_NAME))
            conn.execute(text('CREATE DATABASE "%s"' % SCRATCH_NAME))
    except (ProgrammingError, DBAPIError) as exc:
        admin.dispose()
        pytest.skip("this database user may not create a scratch database: %s" % type(exc).__name__)
    engine_ = create_engine(SCRATCH_URL)
    yield engine_
    engine_.dispose()
    with admin.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % SCRATCH_NAME))
    admin.dispose()


@pytest.fixture(scope="module")
def migrated(scratch):
    alembic("upgrade", REVISION)  # the raynald branch, from an empty database
    return scratch


def snapshot(eng):
    """Everything that defines audit_logs: columns, constraints, indexes, trigger and its function."""
    with eng.connect() as conn:
        def rows(sql):
            return [tuple(r) for r in conn.execute(text(sql)).all()]

        return {
            "columns": rows(
                "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'audit_logs' ORDER BY ordinal_position"
            ),
            "constraints": rows(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.audit_logs'::regclass ORDER BY conname"
            ),
            "indexes": rows(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'audit_logs' ORDER BY indexname"
            ),
            "triggers": rows(
                "SELECT tgname, tgenabled, pg_get_triggerdef(oid) FROM pg_trigger "
                "WHERE tgrelid = 'public.audit_logs'::regclass AND NOT tgisinternal ORDER BY tgname"
            ),
            "function": rows("SELECT pg_get_functiondef('public.audit_logs_reject_change()'::regprocedure)"),
        }


def test_the_migration_builds_what_the_models_build(migrated):
    from_models = snapshot(engine)  # the test database is built with create_all
    from_migration = snapshot(migrated)
    assert len(from_models["columns"]) == 10 and len(from_models["indexes"]) == 4
    assert len(from_models["triggers"]) == 1 and from_models["triggers"][0][1] == "A"
    for part in from_models:
        assert from_migration[part] == from_models[part], part


def test_the_migrated_table_refuses_update_and_delete(migrated):
    with migrated.begin() as conn:
        conn.execute(text("INSERT INTO audit_logs (action) VALUES ('test.event')"))
    for statement in ("UPDATE audit_logs SET action = 'tampered.row'", "DELETE FROM audit_logs"):
        with migrated.connect() as conn:
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(text(statement))
            conn.rollback()
    with migrated.connect() as conn:
        assert conn.execute(text("SELECT action FROM audit_logs")).scalars().all() == ["test.event"]


def test_downgrade_removes_everything_and_upgrade_brings_it_back(migrated):
    before = snapshot(migrated)
    alembic("downgrade", PREVIOUS)
    with migrated.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.audit_logs')")).scalar() is None
        assert conn.execute(text("SELECT to_regprocedure('public.audit_logs_reject_change()')")).scalar() is None
    alembic("upgrade", REVISION)
    assert snapshot(migrated) == before


def test_the_new_revision_is_a_head_and_the_one_before_it_no_longer_is():
    heads = alembic("heads").stdout
    assert REVISION in heads and PREVIOUS not in heads