from test_job import login, make_user
from test_owner import apply_as, new_owner

URL = "/api/v1"
TEXT = "Great experience working with the team."


def accepted_app(client, username="budi"):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, username)
    client.post(URL + "/auth/logout")
    login(client, owner)
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert r.status_code == 200
    client.post(URL + "/auth/logout")
    login(client, username)
    return app_id


def post(client, app_id, **over):
    body = {"application_id": app_id, "content": TEXT, "show_name": True}
    body.update(over)
    return client.post(URL + "/testimonials", json=body)


def admin_login(client):
    make_user(client, "root", "admin")
    login(client, "root")


def test_create_requires_applicant(client):
    assert post(client, "x").status_code == 401
    make_user(client, "alum", "alumni")
    login(client, "alum")
    assert post(client, "x").status_code == 403


def test_create_and_list_mine(client):
    app_id = accepted_app(client)
    r = post(client, app_id)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "application_id", "content", "show_name", "status", "created_at"}
    assert body["status"] == "pending" and body["show_name"] is True
    items = client.get(URL + "/me/testimonials").json()["items"]
    assert [i["id"] for i in items] == [body["id"]]


def test_only_accepted_and_one_per_application(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi")
    r = post(client, app_id)
    assert r.status_code == 409 and r.json()["detail"] == "APPLICATION_NOT_ACCEPTED"
    client.post(URL + "/auth/logout")
    app_id = accepted_app(client, "sari")
    assert post(client, app_id).status_code == 201
    r = post(client, app_id)
    assert r.status_code == 409 and r.json()["detail"] == "TESTIMONIAL_EXISTS"


def test_foreign_application_404(client):
    app_id = accepted_app(client)
    client.post(URL + "/auth/logout")
    make_user(client, "other", "applicant")
    login(client, "other")
    r = post(client, app_id)
    assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"


def test_validation(client):
    app_id = accepted_app(client)
    assert post(client, app_id, content="too short").status_code == 422
    assert post(client, app_id, content="x" * 1001).status_code == 422
    assert post(client, app_id, show_name="true").status_code == 422
    assert post(client, app_id, show_name=1).status_code == 422
    body = {"application_id": app_id, "content": TEXT}
    assert client.post(URL + "/testimonials", json=body).status_code == 422


def test_public_list_only_approved_and_name_hiding(client):
    app1 = accepted_app(client, "budi")
    t1 = post(client, app1).json()["id"]
    client.post(URL + "/auth/logout")
    app2 = accepted_app(client, "sari")
    t2 = post(client, app2, show_name=False).json()["id"]
    client.post(URL + "/auth/logout")
    assert client.get(URL + "/testimonials").json() == {"items": [], "next_cursor": None}

    admin_login(client)
    pending = client.get(URL + "/admin/testimonials", params={"status": "pending"}).json()["items"]
    assert {i["id"] for i in pending} == {t1, t2}
    item = [i for i in pending if i["id"] == t1][0]
    assert item["display_first_name"] == "Budi" and item["display_company"] == "Acme"
    assert item["author_id"]
    for t in (t1, t2):
        r = client.patch("%s/admin/testimonials/%s" % (URL, t), json={"status": "approved"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
    client.post(URL + "/auth/logout")

    items = client.get(URL + "/testimonials").json()["items"]
    by_id = {i["id"]: i for i in items}
    assert by_id[t1]["author"] == {"first_name": "Budi", "company": "Acme"}
    assert by_id[t2]["author"] is None
    assert set(by_id[t1]) == {"id", "content", "created_at", "author"}


def test_moderation_rules(client):
    app_id = accepted_app(client)
    tid = post(client, app_id).json()["id"]
    client.post(URL + "/auth/logout")
    admin_login(client)
    path = "%s/admin/testimonials/%s" % (URL, tid)
    assert client.patch(path, json={"status": "pending"}).status_code == 422
    assert client.patch(path, json={"status": "hidden"}).status_code == 200
    r = client.patch(path, json={"status": "hidden"})
    assert r.status_code == 409 and r.json()["detail"] == "NO_CHANGE"
    assert client.patch(path, json={"status": "approved"}).status_code == 200
    missing = URL + "/admin/testimonials/zzz"
    assert client.patch(missing, json={"status": "hidden"}).status_code == 404
    assert client.get(URL + "/admin/testimonials", params={"status": "bogus"}).status_code == 422
    assert len(client.get(URL + "/admin/testimonials").json()["items"]) == 1
    client.post(URL + "/auth/logout")
    login(client, "budi")
    assert client.get(URL + "/admin/testimonials").status_code == 403
    assert client.patch(path, json={"status": "hidden"}).status_code == 403


def test_delete_own_only(client):
    app_id = accepted_app(client)
    tid = post(client, app_id).json()["id"]
    client.post(URL + "/auth/logout")
    make_user(client, "other", "applicant")
    login(client, "other")
    assert client.delete("%s/testimonials/%s" % (URL, tid)).status_code == 404
    client.post(URL + "/auth/logout")
    login(client, "budi")
    assert client.delete("%s/testimonials/%s" % (URL, tid)).status_code == 204
    assert client.delete("%s/testimonials/%s" % (URL, tid)).status_code == 404
    assert client.get(URL + "/me/testimonials").json() == {"items": []}
    assert post(client, app_id).status_code == 201


def test_public_pagination(client):
    ids = []
    for name in ("user_a", "user_b", "user_c"):
        app_id = accepted_app(client, name)
        ids.append(post(client, app_id).json()["id"])
        client.post(URL + "/auth/logout")
    admin_login(client)
    for t in ids:
        client.patch("%s/admin/testimonials/%s" % (URL, t), json={"status": "approved"})
    client.post(URL + "/auth/logout")
    first = client.get(URL + "/testimonials", params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    params = {"limit": 2, "cursor": first["next_cursor"]}
    second = client.get(URL + "/testimonials", params=params).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    seen = [i["id"] for i in first["items"] + second["items"]]
    assert sorted(seen) == sorted(ids)
    assert client.get(URL + "/testimonials", params={"limit": 51}).status_code == 422
    assert client.get(URL + "/testimonials", params={"cursor": "bad"}).status_code == 422
