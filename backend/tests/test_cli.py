import getpass

import pytest

from app import cli


def test_create_admin_and_login(client):
    user = cli.create_admin("Boss", "secret-pass")
    assert user.role == "admin" and user.status == "active"
    r = client.post("/api/v1/auth/login", json={"username": "boss", "password": "secret-pass"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert client.get("/api/v1/admin/overview").status_code == 200


def test_create_admin_duplicate_and_short_password(client):
    cli.create_admin("boss", "secret-pass")
    with pytest.raises(ValueError):
        cli.create_admin("boss", "another-pass")
    with pytest.raises(ValueError):
        cli.create_admin("boss2", "short")


def test_main_prompts_for_password(client, monkeypatch):
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "secret-pass")
    assert cli.main(["create-admin", "--username", "root1"]) == 0
    assert cli.main(["create-admin", "--username", "root1"]) == 1


def test_main_password_mismatch(client, monkeypatch):
    answers = iter(["secret-pass", "different"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-admin", "--username", "root2"]) == 1
