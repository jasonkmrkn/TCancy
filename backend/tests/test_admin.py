from test_job import job_body, login, make_user

URL = "/api/v1"
ADMIN = URL + "/admin"
PROFILE = {"full_name": "Sari Alumni", "company": "Acme", "angkatan": 2015}


def new_alumni(client, username, profile=True):
    """Register a pending alumni, then log out. profile=False leaves the profile incomplete."""
    r = client.post(
        URL + "/auth/register/alumni",
        json={"username": username, "password": "rahasia123", "profile": PROFILE},
    )
    assert r.status_code == 201
    uid = r.json()["id"]
    if not profile:
        login(client, username)
        assert client.put(URL + "/me/profile", json={}).status_code == 200
        client.post(URL + "/auth/logout")
    return uid


def admin_login(client, username="root"):
    make_user(client, username, "admin")
    login(client, username)


def test_requires_admin(client):
    for method, path in (
        ("get", "/alumni"), ("get", "/users"), ("get", "/overview"),
        ("post", "/alumni/x/approve"), ("patch", "/users/x/status"),
    ):
        assert getattr(client, method)(ADMIN + path).status_code == 401
    make_user(client, "alum", "alumni")
    login(client, "alum")
    assert client.get(ADMIN + "/overview").status_code == 403
    assert client.get(ADMIN + "/users").json()["detail"] == "forbidden"
    client.post(URL + "/auth/logout")
    make_user(client, "pel", "applicant")
    login(client, "pel")
    assert client.get(ADMIN + "/alumni").status_code == 403


def test_unapproved_alumni_cannot_post_then_can(client):
    uid = new_alumni(client, "sari")
    login(client, "sari")
    r = client.post(URL + "/jobs", json=job_body())
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"
    client.post(URL + "/auth/logout")

    admin_login(client)
    r = client.post("%s/alumni/%s/approve" % (ADMIN, uid))
    assert r.status_code == 200
    assert r.json() == {"id": uid, "username": "sari", "role": "alumni", "status": "active"}
    client.post(URL + "/auth/logout")

    login(client, "sari")
    assert client.post(URL + "/jobs", json=job_body()).status_code == 201
    assert client.get(URL + "/me/profile").json()["verification"] == {"state": "approved", "reason": None}


def test_approve_errors(client):
    incomplete = new_alumni(client, "kosong", profile=False)
    done = new_alumni(client, "lengkap")
    admin_login(client)
    r = client.post("%s/alumni/%s/approve" % (ADMIN, incomplete))
    assert r.status_code == 409 and r.json()["detail"] == "PROFILE_INCOMPLETE"
    assert client.post("%s/alumni/%s/approve" % (ADMIN, done)).status_code == 200
    r = client.post("%s/alumni/%s/approve" % (ADMIN, done))
    assert r.status_code == 409 and r.json()["detail"] == "ALREADY_APPROVED"
    for bad in ("00000000-0000-0000-0000-000000000000", "nope"):
        r = client.post("%s/alumni/%s/approve" % (ADMIN, bad))
        assert r.status_code == 404 and r.json()["detail"] == "ALUMNI_NOT_FOUND"
    # A non-alumni user is not an alumni here.
    me = client.get(URL + "/auth/me").json()["id"]
    assert client.post("%s/alumni/%s/approve" % (ADMIN, me)).status_code == 404


def test_approve_suspended(client):
    uid = new_alumni(client, "sari")
    admin_login(client)
    assert client.patch("%s/users/%s/status" % (ADMIN, uid), json={"status": "suspended"}).status_code == 200
    r = client.post("%s/alumni/%s/approve" % (ADMIN, uid))
    assert r.status_code == 409 and r.json()["detail"] == "ACCOUNT_SUSPENDED"


def test_reject_and_reapply(client):
    uid = new_alumni(client, "sari")
    admin_login(client)
    r = client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={})
    assert r.status_code == 422
    r = client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "x" * 501})
    assert r.status_code == 422
    r = client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "Not a graduate"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    r = client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "again"})
    assert r.status_code == 409 and r.json()["detail"] == "NOT_PENDING"
    item = client.get(ADMIN + "/alumni", params={"state": "rejected"}).json()["items"][0]
    assert item["verification"] == {"state": "rejected", "reason": "Not a graduate"}
    client.post(URL + "/auth/logout")

    login(client, "sari")
    assert client.get(URL + "/me/profile").json()["verification"] == {
        "state": "rejected", "reason": "Not a graduate"
    }
    assert client.put(URL + "/me/profile", json=PROFILE).status_code == 200
    assert client.get(URL + "/me/profile").json()["verification"] == {"state": "pending", "reason": None}
    client.post(URL + "/auth/logout")

    admin_login(client, "root2")
    assert client.get(ADMIN + "/alumni", params={"state": "pending"}).json()["items"][0]["id"] == uid
    assert client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "no"}).status_code == 200


def test_reject_approved_not_pending(client):
    uid = new_alumni(client, "sari")
    admin_login(client)
    client.post("%s/alumni/%s/approve" % (ADMIN, uid))
    r = client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "late"})
    assert r.status_code == 409 and r.json()["detail"] == "NOT_PENDING"
    r = client.post("%s/alumni/%s/reject" % (ADMIN, "00000000-0000-0000-0000-000000000000"), json={"reason": "r"})
    assert r.status_code == 404


def test_list_alumni_filters_and_pagination(client):
    a = new_alumni(client, "alum1")
    b = new_alumni(client, "alum2", profile=False)
    c = new_alumni(client, "alum3")
    admin_login(client)
    client.post("%s/alumni/%s/approve" % (ADMIN, c))
    client.post("%s/alumni/%s/reject" % (ADMIN, b), json={"reason": "no"})

    def ids(state):
        return {i["id"] for i in client.get(ADMIN + "/alumni", params={"state": state}).json()["items"]}

    assert ids("pending") == {a} and ids("rejected") == {b} and ids("approved") == {c}
    body = client.get(ADMIN + "/alumni").json()
    assert [i["id"] for i in body["items"]] == [c, b, a]  # newest first
    item = body["items"][2]
    assert set(item) == {
        "id", "username", "account_status", "verification", "full_name", "company",
        "angkatan", "profile_complete", "created_at",
    }
    assert item["profile_complete"] is True and item["account_status"] == "pending"
    assert body["items"][1]["profile_complete"] is False

    first = client.get(ADMIN + "/alumni", params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = client.get(ADMIN + "/alumni", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [i["id"] for i in second["items"]] == [a] and second["next_cursor"] is None
    assert client.get(ADMIN + "/alumni", params={"cursor": "bad"}).status_code == 422
    assert client.get(ADMIN + "/alumni", params={"state": "weird"}).status_code == 422
    assert client.get(ADMIN + "/alumni", params={"limit": 101}).status_code == 422


def test_list_users(client):
    new_alumni(client, "sari")
    make_user(client, "budi", "applicant")
    admin_login(client)
    body = client.get(ADMIN + "/users").json()
    assert {u["username"] for u in body["items"]} == {"sari", "budi", "root"}
    assert set(body["items"][0]) == {"id", "username", "role", "status", "created_at", "last_login_at"}
    assert [u["username"] for u in client.get(ADMIN + "/users", params={"role": "applicant"}).json()["items"]] == ["budi"]
    assert [u["username"] for u in client.get(ADMIN + "/users", params={"status": "pending"}).json()["items"]] == ["sari"]
    assert [u["username"] for u in client.get(ADMIN + "/users", params={"q": "BUD"}).json()["items"]] == ["budi"]
    assert client.get(ADMIN + "/users", params={"q": "%"}).json()["items"] == []
    assert client.get(ADMIN + "/users", params={"q": "x" * 65}).status_code == 422
    assert client.get(ADMIN + "/users", params={"role": "boss"}).status_code == 422
    root = [u for u in client.get(ADMIN + "/users", params={"role": "admin"}).json()["items"]][0]
    assert root["last_login_at"] is not None
    page = client.get(ADMIN + "/users", params={"limit": 2}).json()
    rest = client.get(ADMIN + "/users", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(page["items"]) == 2 and len(rest["items"]) == 1 and rest["next_cursor"] is None


def test_change_user_status(client):
    uid = make_user(client, "budi", "applicant")
    other_admin = make_user(client, "root0", "admin")
    admin_login(client)
    path = "%s/users/%s/status" % (ADMIN, uid)
    r = client.patch(path, json={"status": "suspended"})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    r = client.patch(path, json={"status": "suspended"})
    assert r.status_code == 409 and r.json()["detail"] == "NO_CHANGE"
    # A suspended user cannot log in; reactivation restores access.
    client.post(URL + "/auth/logout")
    r = client.post(URL + "/auth/login", json={"username": "budi", "password": "rahasia123"})
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_SUSPENDED"
    login(client, "root")
    assert client.patch(path, json={"status": "active"}).json()["status"] == "active"
    login(client, "budi")
    client.post(URL + "/auth/logout")
    login(client, "root")

    r = client.patch("%s/users/%s/status" % (ADMIN, other_admin), json={"status": "suspended"})
    assert r.status_code == 403 and r.json()["detail"] == "CANNOT_MODIFY_ADMIN"
    me = client.get(URL + "/auth/me").json()["id"]
    assert client.patch("%s/users/%s/status" % (ADMIN, me), json={"status": "suspended"}).status_code == 403
    for bad in ("00000000-0000-0000-0000-000000000000", "nope"):
        r = client.patch("%s/users/%s/status" % (ADMIN, bad), json={"status": "active"})
        assert r.status_code == 404 and r.json()["detail"] == "USER_NOT_FOUND"
    assert client.patch(path, json={"status": "pending"}).status_code == 422
    assert client.patch(path, json={}).status_code == 422


def test_reactivating_unverified_alumni_stays_pending(client):
    uid = new_alumni(client, "sari")
    admin_login(client)
    path = "%s/users/%s/status" % (ADMIN, uid)
    # Pending alumni asked to become "active" would skip approval: nothing changes.
    r = client.patch(path, json={"status": "active"})
    assert r.status_code == 409 and r.json()["detail"] == "NO_CHANGE"
    assert client.patch(path, json={"status": "suspended"}).status_code == 200
    r = client.patch(path, json={"status": "active"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    # An approved alumni returns to active.
    client.post("%s/alumni/%s/approve" % (ADMIN, uid))
    client.patch(path, json={"status": "suspended"})
    assert client.patch(path, json={"status": "active"}).json()["status"] == "active"


def test_overview(client):
    new_alumni(client, "sari")
    new_alumni(client, "kosong", profile=False)
    make_user(client, "budi", "applicant")
    admin_login(client)
    body = client.get(ADMIN + "/overview").json()
    assert set(body) == {
        "users_by_role", "users_by_status", "jobs_by_status", "applications_by_status",
        "documents_by_type", "alumni_awaiting_decision",
    }
    assert body["users_by_role"] == {"applicant": 1, "alumni": 2, "admin": 1}
    assert body["users_by_status"] == {"pending": 2, "active": 2, "suspended": 0}
    assert body["jobs_by_status"] == {"open": 0, "closed": 0}
    assert body["applications_by_status"] == {
        "submitted": 0, "shortlisted": 0, "accepted": 0, "rejected": 0, "withdrawn": 0
    }
    assert body["documents_by_type"] == {"cv": 0, "ktp": 0, "intro_video": 0}
    assert body["alumni_awaiting_decision"] == 2
    uid = client.get(ADMIN + "/alumni", params={"state": "pending"}).json()["items"][0]["id"]
    client.post("%s/alumni/%s/reject" % (ADMIN, uid), json={"reason": "no"})
    assert client.get(ADMIN + "/overview").json()["alumni_awaiting_decision"] == 1
