import ast
import inspect
import pathlib
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import audit, config
from app.db import engine
from app.models import AuditLog, Base


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


def rows(session):
    return session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)).all()


def count_elsewhere():
    """Rows as another connection sees them (so only what was committed)."""
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM audit_logs")).scalar()


def add(session, n=3, **over):
    for i in range(n):
        audit.record(session, actor_id=uuid.uuid4(), actor_role="applicant", action="test.event", **over)
    session.commit()


def req(peer="203.0.113.9", user_agent=None, forwarded=None):
    headers = []
    if user_agent is not None:
        headers.append((b"user-agent", user_agent.encode("latin-1")))
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request({"type": "http", "client": (peer, 5000), "headers": headers})


# --- record: the frozen interface -----------------------------------------------


def test_the_signature_is_the_frozen_one():
    params = inspect.signature(audit.record).parameters
    assert list(params) == [
        "db", "actor_id", "actor_role", "action", "target_type", "target_id", "ip", "user_agent", "details",
    ]
    assert params["db"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for name, p in params.items() if name != "db")
    assert {n for n, p in params.items() if p.default is inspect.Parameter.empty} == {
        "db", "actor_id", "actor_role", "action",
    }


def test_record_writes_one_row_and_returns_none(session):
    actor, target = uuid.uuid4(), uuid.uuid4()
    result = audit.record(
        session, actor_id=actor, actor_role="alumni", action="job.close", target_type="job", target_id=target,
        ip="203.0.113.7", user_agent="pytest/1.0", details=audit.details(["status"], count=2),
    )
    session.commit()
    assert result is None
    (row,) = rows(session)
    assert (row.actor_id, row.actor_role, row.action) == (actor, "alumni", "job.close")
    assert (row.target_type, row.target_id, row.ip, row.user_agent) == ("job", target, "203.0.113.7", "pytest/1.0")
    assert row.details == {"fields": ["status"], "count": 2}
    assert row.id is not None and row.created_at is not None


def test_only_the_required_arguments_are_needed(session):
    audit.record(session, actor_id=None, actor_role=None, action="system.started")
    session.commit()
    (row,) = rows(session)
    assert row.actor_id is None and row.target_id is None and row.details is None and row.ip is None


def test_ids_may_be_given_as_text(session):
    ident = uuid.uuid4()
    audit.record(session, actor_id=str(ident), actor_role=None, action="test.event", target_id=str(ident))
    session.commit()
    assert rows(session)[0].actor_id == ident


# --- record never commits -------------------------------------------------------


def test_the_row_is_visible_to_the_caller_but_not_to_others_until_the_caller_commits(session):
    audit.record(session, actor_id=None, actor_role=None, action="test.event")
    assert len(rows(session)) == 1  # same transaction: visible
    assert count_elsewhere() == 0  # not committed
    session.commit()
    assert count_elsewhere() == 1


def test_a_rollback_takes_the_row_with_it(session):
    audit.record(session, actor_id=None, actor_role=None, action="test.event")
    session.rollback()
    assert count_elsewhere() == 0 and rows(session) == []


def test_the_row_is_saved_or_lost_with_the_callers_other_work(session):
    from app.models import User

    user = User(username="atomic", password_hash="x", role="applicant", status="active")
    session.add(user)
    session.flush()
    audit.record(session, actor_id=user.id, actor_role="applicant", action="auth.register")
    session.rollback()
    assert count_elsewhere() == 0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0


# --- record: what it refuses ----------------------------------------------------


@pytest.mark.parametrize("action", ["auth.login", "account.delete", "job.close_all", "a.b.c", "contract.minimal"])
def test_actions_that_look_like_actions_are_accepted(session, action):
    audit.record(session, actor_id=None, actor_role=None, action=action)


@pytest.mark.parametrize(
    "action", ["login", "Auth.login", "auth.", ".login", "auth login", "auth.log-in", "", " auth.login", None, 5, "a." + "b" * 70]
)
def test_other_actions_are_refused(session, action):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action=action)
    assert rows(session) == []


@pytest.mark.parametrize("role", ["Admin", "a b", "x" * 41, 5, "alumni; DROP"])
def test_a_role_must_be_a_short_lower_case_name(session, role):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=role, action="test.event")


@pytest.mark.parametrize("target_type", ["User", "refresh family", "x" * 41, 5])
def test_a_target_type_must_be_a_short_lower_case_name(session, target_type):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action="test.event", target_type=target_type)


@pytest.mark.parametrize("bad", ["nope", 5, "12345678-1234-1234-1234", b"x"])
def test_ids_must_be_uuids(session, bad):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=bad, actor_role=None, action="test.event")
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action="test.event", target_id=bad)


# --- record: text that comes from outside ---------------------------------------


def stored_user_agent(session, value):
    audit.record(session, actor_id=None, actor_role=None, action="test.event", user_agent=value)
    session.commit()
    return rows(session)[-1].user_agent


def test_a_nul_byte_does_not_stop_the_row_being_written(session):
    # PostgreSQL refuses text with NUL; unchecked, a header could make every failed login a 500.
    assert stored_user_agent(session, "Mozilla/5.0\x00 (X11)") == "Mozilla/5.0 (X11)"


def test_control_characters_and_line_breaks_are_removed(session):
    assert stored_user_agent(session, "curl/8\r\nX-Injected: yes\t\x07\x1b[31m") == "curl/8X-Injected: yes[31m"
    assert stored_user_agent(session, "a\u2028b\u2029c\x85d") == "abcd"


def test_text_is_cut_to_size_and_empty_text_becomes_null(session):
    assert len(stored_user_agent(session, "A" * 10_000)) == 256
    assert stored_user_agent(session, "   \x00\r\n ") is None
    assert stored_user_agent(session, "") is None


def test_unicode_survives_and_lone_surrogates_are_dropped(session):
    assert stored_user_agent(session, "Peramban-ñ-日本") == "Peramban-ñ-日本"
    assert stored_user_agent(session, "ok\ud800end") == "okend"


def test_an_ip_is_cut_to_size_and_cleaned_too(session):
    audit.record(session, actor_id=None, actor_role=None, action="test.event", ip="1" * 200 + "\x00")
    session.commit()
    assert len(rows(session)[0].ip) == 64


def test_text_arguments_must_be_text(session):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action="test.event", user_agent=b"bytes")
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action="test.event", ip=5)


# --- record: the shape of details -----------------------------------------------


def stored_details(session, value):
    audit.record(session, actor_id=None, actor_role=None, action="test.event", details=value)
    session.commit()
    return rows(session)[-1].details


def test_the_contract_example_is_accepted(session):
    assert stored_details(session, {"reason": "contract", "count": 2}) == {"reason": "contract", "count": 2}


def test_numbers_words_and_lists_of_words_are_accepted(session):
    value = {"count": 3, "negative": -1, "kind": "bad_password", "fields": ["full_name", "phone"]}
    assert stored_details(session, value) == value


def test_nothing_or_nothing_in_it_is_stored_as_null(session):
    assert stored_details(session, None) is None
    assert stored_details(session, {}) is None


@pytest.mark.parametrize(
    "value",
    [
        {"count": 1.5}, {"count": True}, {"count": float("nan")}, {"count": 2**60},
        {"note": "hello world"}, {"note": "budi@example.com"}, {"note": "Rahasia123"}, {"note": ""},
        {"note": "x" * 65}, {"nested": {"a": 1}}, {"items": [1, 2]}, {"items": ["ok", {"a": 1}]},
        {"items": ["a"] * 51}, {"Count": 1}, {"has space": 1}, {"": 1}, {1: 1}, {"k": None}, {"k": b"x"},
        {"k" + str(i): i for i in range(300)},
        "just text", ["a"], 5,
    ],
)
def test_other_shapes_are_refused(session, value):
    with pytest.raises(ValueError):
        audit.record(session, actor_id=None, actor_role=None, action="test.event", details=value)
    assert rows(session) == []


def test_the_error_never_repeats_the_rejected_value(session):
    secret = "Rahasia123 hunter2"
    with pytest.raises(ValueError) as caught:
        audit.record(session, actor_id=None, actor_role=None, action="test.event", details={"note": secret})
    assert "hunter2" not in str(caught.value) and "Rahasia" not in str(caught.value)


# --- details(): the strict helper -----------------------------------------------


def test_details_takes_field_names_and_counts():
    assert audit.details(["status", "title"], count=2, skipped=0) == {
        "fields": ["status", "title"], "count": 2, "skipped": 0,
    }
    assert audit.details() == {}
    assert audit.details(count=-3) == {"count": -3}


def test_field_names_are_sorted_and_unique():
    assert audit.details(["title", "status", "title"]) == {"fields": ["status", "title"]}
    assert audit.details(("status",)) == {"fields": ["status"]}
    assert audit.details({"status"}) == {"fields": ["status"]}


def test_every_column_in_the_database_is_a_known_field_without_listing_it_anywhere():
    names = {c.name for t in Base.metadata.tables.values() for c in t.columns}
    assert len(names) > 40
    assert audit.details(sorted(names))["fields"] == sorted(names)


def test_a_column_added_later_is_known_at_once():
    from sqlalchemy import Column, Table, Text

    table = Table("tmp_audit_probe", Base.metadata, Column("a_brand_new_field", Text), Column("id", Text, primary_key=True))
    try:
        assert audit.details(["a_brand_new_field"]) == {"fields": ["a_brand_new_field"]}
    finally:
        Base.metadata.remove(table)
    with pytest.raises(ValueError):
        audit.details(["a_brand_new_field"])


@pytest.mark.parametrize("name", ["full_name", "email", "phone", "nik", "address", "birth_date", "password", "profile", "documents"])
def test_the_personal_fields_that_are_not_columns_are_known(name):
    assert audit.details([name]) == {"fields": [name]}


@pytest.mark.parametrize(
    "fields",
    [["budi"], ["rahasia123"], ["budi@example.com"], ["not a field"], ["Status"], [""], [5], [None], [["status"]], "status", b"status"],
)
def test_anything_that_is_not_a_known_field_name_is_refused(fields):
    with pytest.raises(ValueError):
        audit.details(fields)


@pytest.mark.parametrize("count", [1.5, True, "3", None, [1], 2**60, float("inf")])
def test_counts_must_be_plain_integers(count):
    with pytest.raises(ValueError):
        audit.details(count=count)


@pytest.mark.parametrize("key", ["Count", "a b", "fields", "9lives", "x" * 41])
def test_count_names_must_be_plain_and_not_collide(key):
    with pytest.raises(ValueError):
        audit.details(**{key: 1})


def test_what_details_returns_is_always_acceptable_to_record(session):
    value = audit.details(["status", "password"], revoked=3)
    audit.record(session, actor_id=None, actor_role=None, action="test.event", details=value)
    session.commit()
    assert rows(session)[0].details == value


def test_details_error_does_not_repeat_the_value():
    with pytest.raises(ValueError) as caught:
        audit.details(["hunter2-secret"])
    assert "hunter2" not in str(caught.value)


# --- client(): ip and user agent of a request -----------------------------------


def test_client_gives_the_peer_and_the_user_agent():
    assert audit.client(req("203.0.113.9", "pytest/1.0")) == {"ip": "203.0.113.9", "user_agent": "pytest/1.0"}


def test_client_has_no_user_agent_when_none_was_sent():
    assert audit.client(req())["user_agent"] is None


def test_client_keeps_ipv6_in_full(monkeypatch):
    assert audit.client(req("2001:db8:1:2:aaaa:bbbb:cccc:dddd"))["ip"] == "2001:db8:1:2:aaaa:bbbb:cccc:dddd"


def test_client_follows_the_trusted_proxy_rules_of_the_rate_limiter(monkeypatch):
    import ipaddress

    monkeypatch.setattr(config, "TRUSTED_PROXIES", (ipaddress.ip_network("172.18.0.0/16"),))
    assert audit.client(req("172.18.0.2", forwarded="6.6.6.6, 2001:db8::7"))["ip"] == "2001:db8::7"
    assert audit.client(req("203.0.113.9", forwarded="6.6.6.6"))["ip"] == "203.0.113.9"


# --- the database refuses to change or remove an entry --------------------------


def snapshot(session):
    return [(r.id, r.action, r.ip, r.details) for r in rows(session)]


def refused(statement, params=None, *, executemany=False):
    with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(statement), params or {})
        conn.rollback()


@pytest.fixture
def three(session):
    add(session, 3, ip="203.0.113.1")
    return snapshot(session)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_logs SET action = 'tampered.row'",
        "UPDATE audit_logs SET action = 'tampered.row' WHERE id = (SELECT id FROM audit_logs LIMIT 1)",
        "UPDATE audit_logs SET ip = NULL, details = NULL, user_agent = NULL, actor_id = NULL",
        "UPDATE audit_logs SET created_at = created_at - interval '1 year'",
        "UPDATE audit_logs SET action = 'tampered.row' WHERE false",
        "DELETE FROM audit_logs",
        "DELETE FROM audit_logs WHERE id = (SELECT id FROM audit_logs LIMIT 1)",
        "DELETE FROM audit_logs WHERE created_at < now() + interval '1 day'",
        "DELETE FROM audit_logs WHERE false",
        "DELETE FROM audit_logs USING audit_logs a2 WHERE audit_logs.id = a2.id",
    ],
    ids=["update-all", "update-one", "update-columns", "update-time", "update-nothing",
         "delete-all", "delete-one", "delete-by-time", "delete-nothing", "delete-using"],
)
def test_update_and_delete_statements_are_refused_and_nothing_changes(session, three, statement):
    refused(statement)
    session.expire_all()
    assert snapshot(session) == three


def test_an_upsert_cannot_overwrite_an_entry(session, three):
    refused(
        "INSERT INTO audit_logs (id, action) VALUES (:id, 'tampered.row') ON CONFLICT (id) DO UPDATE SET action = 'tampered.row'",
        {"id": three[0][0]},
    )
    session.expire_all()
    assert snapshot(session) == three


def test_many_updates_in_one_call_are_refused(session, three):
    with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(
                text("UPDATE audit_logs SET ip = :ip WHERE id = :id"),
                [{"ip": "6.6.6.6", "id": row[0]} for row in three],
            )
        conn.rollback()
    session.expire_all()
    assert snapshot(session) == three


def test_the_orm_cannot_change_an_entry(session, three):
    row = session.get(AuditLog, three[0][0])
    row.action = "tampered.row"
    with pytest.raises(DBAPIError, match="append-only"):
        session.commit()
    session.rollback()
    session.expire_all()
    assert snapshot(session) == three


def test_the_orm_cannot_delete_an_entry(session, three):
    session.delete(session.get(AuditLog, three[0][0]))
    with pytest.raises(DBAPIError, match="append-only"):
        session.commit()
    session.rollback()
    session.expire_all()
    assert snapshot(session) == three


def test_a_refused_change_inside_a_transaction_takes_that_transaction_down(session):
    audit.record(session, actor_id=None, actor_role=None, action="test.first")
    session.commit()
    audit.record(session, actor_id=None, actor_role=None, action="test.second")
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("UPDATE audit_logs SET action = 'tampered.row'"))
    session.rollback()
    assert [r.action for r in rows(session)] == ["test.first"]


def test_inserting_still_works(session, three):
    add(session, 2)
    assert len(rows(session)) == 5


def test_the_trigger_stays_on_when_replication_mode_would_switch_triggers_off(session, three):
    with engine.connect() as conn:
        try:
            conn.execute(text("SET session_replication_role = replica"))
        except (ProgrammingError, DBAPIError):
            conn.rollback()
            pytest.skip("the test database user may not change session_replication_role")
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("UPDATE audit_logs SET action = 'tampered.row'"))
        conn.rollback()


def test_the_trigger_is_installed_the_way_the_migration_installs_it():
    with engine.connect() as conn:
        found = conn.execute(text(
            "SELECT tgenabled, pg_get_triggerdef(oid) FROM pg_trigger "
            "WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal"
        )).all()
    assert len(found) == 1
    enabled, definition = found[0]
    assert enabled == "A"  # ENABLE ALWAYS
    assert "BEFORE DELETE OR UPDATE" in definition and "FOR EACH STATEMENT" in definition


# --- every call to record() in the app builds details with details() ------------

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def audit_names(tree):
    """Which local names mean the audit module, and which mean its functions."""
    modules, functions = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "app":
                modules.update(a.asname or a.name for a in node.names if a.name == "audit")
            elif node.module == "app.audit":
                functions.update({a.asname or a.name: a.name for a in node.names})
        elif isinstance(node, ast.Import):
            modules.update(a.asname for a in node.names if a.name == "app.audit" and a.asname)
    return modules, functions


def audit_function(node, modules, functions):
    """'record', 'details', 'client' when `node` refers to that function of app.audit, else None."""
    if isinstance(node, ast.Attribute):
        owner = node.value
        if isinstance(owner, ast.Name) and owner.id in modules:
            return node.attr
        if isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Name) and (owner.value.id, owner.attr) == ("app", "audit"):
            return node.attr
    if isinstance(node, ast.Name) and node.id in functions:
        return functions[node.id]
    return None


def check_record_calls(source):
    """[(line, problem or None)] for every use of audit.record in `source`."""
    tree = ast.parse(source)
    modules, functions = audit_names(tree)
    called = set()
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(id(node.func))
            if audit_function(node.func, modules, functions) != "record":
                continue
            problem = None
            if len(node.args) > 1:
                problem = "arguments other than db must be keywords"
            for keyword in node.keywords:
                value = keyword.value
                if keyword.arg is None:
                    if not (isinstance(value, ast.Call) and audit_function(value.func, modules, functions) == "client"):
                        problem = "** is only allowed with audit.client(...)"
                elif keyword.arg == "details":
                    is_none = isinstance(value, ast.Constant) and value.value is None
                    from_helper = isinstance(value, ast.Call) and audit_function(value.func, modules, functions) == "details"
                    if not (is_none or from_helper):
                        problem = "details must be None or audit.details(...)"
            found.append((node.lineno, problem))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)) and id(node) not in called:
            if audit_function(node, modules, functions) == "record" and not isinstance(node, ast.Name):
                found.append((node.lineno, "audit.record must be called, not passed around"))
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and audit_function(node, modules, functions) == "record":
                found.append((node.lineno, "record must be called, not passed around"))
    return found


GOOD = [
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y")',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", details=None)',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", details=audit.details(["status"], count=1))',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", **audit.client(request))',
    'from app.audit import record, details\nrecord(db, actor_id=1, actor_role="a", action="x.y", details=details(count=1))',
    'from app import audit as a\na.record(db, actor_id=1, actor_role="a", action="x.y", details=a.details(count=1))',
    'import app.audit\napp.audit.record(db, actor_id=1, actor_role="a", action="x.y", details=app.audit.details(count=1))',
    'import other\nother.record(db, details={"a": "b"})',
]
BAD = [
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", details={"count": 1})',
    'from app import audit\nd = {"a": 1}\naudit.record(db, actor_id=1, actor_role="a", action="x.y", details=d)',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", details=other.details(count=1))',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", **extra)',
    'from app import audit\naudit.record(db, actor_id=1, actor_role="a", action="x.y", **audit.details(count=1))',
    'from app import audit\naudit.record(db, 1, "a", "x.y")',
    'from app import audit\nrec = audit.record\nrec(db, actor_id=1, actor_role="a", action="x.y", details={"a": "b"})',
    'from app.audit import record\nr = record\nr(db, actor_id=1, actor_role="a", action="x.y", details={"a": "b"})',
    'from app.audit import record as r\nr(db, actor_id=1, actor_role="a", action="x.y", details={"a": "b"})',
    'import app.audit\napp.audit.record(db, actor_id=1, actor_role="a", action="x.y", details={"a": "b"})',
    'from app import audit as a\na.record(db, actor_id=1, actor_role="a", action="x.y", details=str(1))',
]


@pytest.mark.parametrize("source", GOOD)
def test_the_scanner_accepts_calls_that_use_the_helper(source):
    assert all(problem is None for _, problem in check_record_calls(source))


@pytest.mark.parametrize("source", BAD)
def test_the_scanner_catches_calls_that_bypass_the_helper(source):
    assert any(problem for _, problem in check_record_calls(source))


def test_the_scanner_counts_the_calls_it_sees():
    source = GOOD[0] + "\n" + GOOD[2].split("\n", 1)[1]
    assert len(check_record_calls(source)) == 2


def test_every_call_to_audit_record_in_the_app_takes_details_from_the_helper_or_none():
    problems, calls = [], 0
    for path in sorted(APP.rglob("*.py")):
        if path in (APP / "audit.py", APP / "auditing.py"):
            continue
        for line, problem in check_record_calls(path.read_text()):
            calls += 1
            if problem:
                problems.append("%s:%d %s" % (path.relative_to(APP.parent), line, problem))
    assert problems == [], "\n".join(problems)
    assert calls >= 6, "the scanner should see at least the six calls this stage installed"

def test_auditing_log_is_the_only_wrapper_and_uses_audit_client():
    source = (APP / "auditing.py").read_text()
    found = check_record_calls(source)
    assert len(found) == 1
    assert "**audit.client(request)" in source