"""GET /api/v1/admin/audit-logs"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import audit
from app.db import engine
from test_audit_events import entries, forget
from test_job import login, make_user

URL = "/api/v1/admin/audit-logs"
BASE = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
KEYS = ["id", "created_at", "action", "actor_id", "actor_role", "target_type", "target_id", "ip", "details"]


def admin(client):
    make_user(client, "root", "admin")
    login(client, "root")
    forget()  # start from an empty log, without the entries that signing in just wrote


def put(action="test.event", at=BASE, **over):
    """Insert an entry with a chosen time (and id), the way only the database can."""
    row = {
        "id": uuid.uuid4(), "actor_id": None, "actor_role": None, "action": action, "target_type": None,
        "target_id": None, "ip": None, "user_agent": None, "details": None, "created_at": at, **over,
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs (id, actor_id, actor_role, action, target_type, target_id, ip, user_agent, details, created_at) "
                "VALUES (:id, :actor_id, :actor_role, :action, :target_type, :target_id, :ip, :user_agent, CAST(:details AS jsonb), :created_at)"
            ),
            {**row, "details": json.dumps(row["details"]) if row["details"] is not None else None},
        )
    return row


def ids(response):
    return [item["id"] for item in response.json()["items"]]


def get(client, **params):
    return client.get(URL, params=params)


# --- who may read ---------------------------------------------------------------


def test_the_log_needs_an_admin(client):
    assert client.get(URL).status_code == 401
    make_user(client, "pel", "applicant")
    login(client, "pel")
    r = client.get(URL)
    assert r.status_code == 403 and r.json()["detail"] == "forbidden"
    client.post("/api/v1/auth/logout")
    make_user(client, "alum", "alumni")
    login(client, "alum")
    assert client.get(URL).status_code == 403


def test_a_pending_or_suspended_admin_cannot_read_it(client):
    make_user(client, "waiting", "admin", status="pending")
    login(client, "waiting")
    r = client.get(URL)
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"
    client.post("/api/v1/auth/logout")
    make_user(client, "gone", "admin")
    login(client, "gone")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'suspended' WHERE username = 'gone'"))
    r = client.get(URL)
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_SUSPENDED"


def test_an_active_admin_can_read_it(client):
    admin(client)
    assert client.get(URL).status_code == 200


# --- what an entry looks like ---------------------------------------------------


def test_an_entry_has_exactly_the_documented_fields_and_no_user_agent(client):
    admin(client)
    actor, target = uuid.uuid4(), uuid.uuid4()
    put("job.close", actor_id=actor, actor_role="alumni", target_type="job", target_id=target, ip="203.0.113.7",
        user_agent="Mozilla/5.0 (secret agent)", details={"fields": ["status"], "count": 2})
    r = client.get(URL)
    (item,) = r.json()["items"]
    assert list(item) == KEYS
    assert item["action"] == "job.close" and item["actor_id"] == str(actor) and item["actor_role"] == "alumni"
    assert item["target_type"] == "job" and item["target_id"] == str(target) and item["ip"] == "203.0.113.7"
    assert item["details"] == {"fields": ["status"], "count": 2}
    assert item["created_at"] == BASE.isoformat()
    assert "user_agent" not in r.text and "secret agent" not in r.text
    assert entries("job.close")[0]["user_agent"] == "Mozilla/5.0 (secret agent)"  # but it is kept


def test_empty_fields_come_back_as_null(client):
    admin(client)
    put()
    (item,) = client.get(URL).json()["items"]
    assert [item[k] for k in ("actor_id", "actor_role", "target_type", "target_id", "ip", "details")] == [None] * 6


def test_the_response_is_not_cacheable_and_has_the_security_headers(client):
    admin(client)
    r = client.get(URL)
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert r.json() == {"items": [], "next_cursor": None}


def test_reading_the_log_writes_nothing_to_it(client):
    admin(client)
    put()
    client.get(URL)
    client.get(URL, params={"action": "test.event"})
    assert len(entries()) == 1


def test_the_admins_own_login_shows_up(client):
    make_user(client, "root", "admin")
    login(client, "root")
    items = client.get(URL, params={"action": "auth.login"}).json()["items"]
    assert len(items) == 1 and items[0]["actor_role"] == "admin" and items[0]["details"] is None


# --- order ----------------------------------------------------------------------


def test_newest_first_and_ties_are_broken_by_id(client):
    admin(client)
    old = put(at=BASE)
    new = put(at=BASE + timedelta(minutes=5))
    tie_a = put(at=BASE + timedelta(minutes=2))
    tie_b = put(at=BASE + timedelta(minutes=2))
    first, second = sorted([tie_a["id"], tie_b["id"]], reverse=True)
    assert ids(client.get(URL)) == [str(new["id"]), str(first), str(second), str(old["id"])]


# --- filters --------------------------------------------------------------------


def test_filter_by_action_is_exact(client):
    admin(client)
    a, b = put("auth.login"), put("auth.login_failed")
    put("auth.logout")
    assert ids(get(client, action="auth.login")) == [str(a["id"])]
    assert ids(get(client, action="auth.login_failed")) == [str(b["id"])]
    assert ids(get(client, action="auth.")) == [] and ids(get(client, action="auth")) == []
    assert ids(get(client, action="no.such")) == []


def test_filter_by_actor_and_by_target(client):
    admin(client)
    me, you, thing = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = put(actor_id=me, target_id=thing)
    b = put(actor_id=you, target_id=thing)
    c = put(actor_id=me)
    assert set(ids(get(client, actor_id=str(me)))) == {str(a["id"]), str(c["id"])}
    assert set(ids(get(client, target_id=str(thing)))) == {str(a["id"]), str(b["id"])}
    assert ids(get(client, actor_id=str(me), target_id=str(thing))) == [str(a["id"])]
    assert ids(get(client, actor_id=str(uuid.uuid4()))) == []


def test_filters_combine(client):
    admin(client)
    me = uuid.uuid4()
    hit = put("auth.login", actor_id=me)
    put("auth.logout", actor_id=me)
    put("auth.login", actor_id=uuid.uuid4())
    assert ids(get(client, action="auth.login", actor_id=str(me))) == [str(hit["id"])]


def test_since_is_included_and_until_is_not(client):
    admin(client)
    rows = [put(at=BASE + timedelta(hours=h)) for h in range(5)]  # 12:00 .. 16:00
    since, until = BASE + timedelta(hours=1), BASE + timedelta(hours=3)
    wanted = [str(rows[2]["id"]), str(rows[1]["id"])]
    assert ids(get(client, since=since.isoformat(), until=until.isoformat())) == wanted
    assert ids(get(client, since=since.isoformat())) == [str(r["id"]) for r in reversed(rows[1:])]
    assert ids(get(client, until=until.isoformat())) == [str(r["id"]) for r in reversed(rows[:3])]
    assert ids(get(client, since=until.isoformat(), until=until.isoformat())) == []
    assert ids(get(client, since=until.isoformat(), until=since.isoformat())) == []  # reversed: nothing, not an error


def test_a_time_without_a_zone_is_utc_and_other_zones_are_converted(client):
    admin(client)
    row = put(at=BASE)  # 12:00 UTC
    assert ids(get(client, since="2026-10-01T12:00:00")) == [str(row["id"])]
    assert ids(get(client, since="2026-10-01T12:00:01")) == []
    assert ids(get(client, until="2026-10-01T12:00:00")) == []
    assert ids(get(client, since="2026-10-01T19:00:00+07:00", until="2026-10-01T19:00:01+07:00")) == [str(row["id"])]
    assert ids(get(client, since="2026-10-01")) == [str(row["id"])]  # a date alone is midnight UTC


@pytest.mark.parametrize(
    "params",
    [{"actor_id": "nope"}, {"target_id": "123"}, {"since": "yesterday"}, {"until": "2026-13-45T00:00:00"}, {"action": "x" * 65},
     {"limit": 0}, {"limit": -1}, {"limit": 201}, {"limit": "many"}, {"cursor": "x" * 201}],
)
def test_bad_parameters_are_422(client, params):
    admin(client)
    assert get(client, **params).status_code == 422


def test_the_422_does_not_echo_what_was_sent(client):
    admin(client)
    r = get(client, actor_id="hunter2-secret")
    assert r.status_code == 422 and "hunter2" not in r.text


# --- limit and cursor -----------------------------------------------------------


def fill(n, **over):
    return [put(at=BASE + timedelta(seconds=i), **over) for i in range(n)]


def test_the_default_limit_is_50_and_the_biggest_is_200(client):
    admin(client)
    fill(210)
    r = client.get(URL)
    assert len(r.json()["items"]) == 50 and r.json()["next_cursor"]
    r = get(client, limit=200)
    assert len(r.json()["items"]) == 200 and r.json()["next_cursor"]
    assert len(get(client, limit=1).json()["items"]) == 1


def test_exactly_a_full_page_has_no_next_cursor(client):
    admin(client)
    fill(5)
    r = get(client, limit=5)
    assert len(r.json()["items"]) == 5 and r.json()["next_cursor"] is None
    assert get(client, limit=6).json()["next_cursor"] is None


def walk(client, limit, **params):
    seen, cursor, pages = [], None, 0
    while True:
        extra = {"cursor": cursor} if cursor else {}
        body = get(client, limit=limit, **params, **extra).json()
        seen += ids_of(body)
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return seen, pages
        assert pages < 100


def ids_of(body):
    return [item["id"] for item in body["items"]]


def test_walking_the_cursor_gives_every_entry_once_in_order(client):
    admin(client)
    rows = fill(23)
    seen, pages = walk(client, 7)
    assert pages == 4
    assert seen == [str(r["id"]) for r in reversed(rows)]


def test_entries_with_the_same_time_are_neither_repeated_nor_skipped_at_a_page_boundary(client):
    admin(client)
    same = [put(at=BASE) for _ in range(12)]
    older = put(at=BASE - timedelta(minutes=1))
    newer = put(at=BASE + timedelta(minutes=1))
    for limit in (1, 2, 5, 12, 13):
        seen, _ = walk(client, limit)
        assert len(seen) == len(set(seen)) == 14, limit
        assert seen[0] == str(newer["id"]) and seen[-1] == str(older["id"]), limit
        assert set(seen[1:-1]) == {str(r["id"]) for r in same}


def test_the_cursor_works_with_filters(client):
    admin(client)
    me = uuid.uuid4()
    mine = [put("auth.login", at=BASE + timedelta(seconds=i), actor_id=me) for i in range(9)]
    for i in range(9):
        put("auth.logout", at=BASE + timedelta(seconds=i), actor_id=me)
    seen, pages = walk(client, 4, action="auth.login", actor_id=str(me))
    assert pages == 3 and seen == [str(r["id"]) for r in reversed(mine)]


def test_the_cursor_is_the_same_format_as_the_other_endpoints(client):
    from app import jobs

    admin(client)
    rows = fill(3)
    cursor = get(client, limit=2).json()["next_cursor"]
    created_at, ident = jobs.decode_cursor(cursor)
    assert ident == rows[1]["id"] and created_at == rows[1]["created_at"]  # the last entry of the first page


@pytest.mark.parametrize("cursor", ["!!!", "bm90LWEtY3Vyc29y", "", "YQ=="])
def test_a_broken_cursor_is_422(client, cursor):
    admin(client)
    fill(3)
    r = get(client, cursor=cursor) if cursor else get(client)
    assert r.status_code == (422 if cursor else 200)
    if cursor:
        assert r.json()["detail"] == "invalid cursor"


def test_entries_written_after_the_first_page_do_not_disturb_the_next_one(client):
    admin(client)
    rows = fill(6)
    first = get(client, limit=3).json()
    put(at=BASE + timedelta(hours=1))  # something new arrives at the top meanwhile
    second = get(client, limit=3, cursor=first["next_cursor"]).json()
    assert ids_of(first) + ids_of(second) == [str(r["id"]) for r in reversed(rows)]
    assert second["next_cursor"] is None


def test_a_time_without_a_zone_is_made_utc_before_it_reaches_the_database():
    # The database's own time zone must not decide what a bare time means.
    from app.routers.admin_audit import _utc

    bare = datetime(2026, 10, 1, 12, 0, 0)
    assert _utc(bare) == datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _utc(bare).utcoffset() == timedelta(0)
    zoned = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    assert _utc(zoned) is zoned
    assert _utc(None) is None