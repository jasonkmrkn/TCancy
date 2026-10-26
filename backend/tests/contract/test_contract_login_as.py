"""Contract for tests/helpers.login_as: returns a dict of headers and does not raise."""
from helpers import login_as, make_profile

AUTH = "/api/v1/auth"


def test_login_as_returns_headers_for_a_valid_user(client):
    r = client.post(
        AUTH + "/register",
        json={"username": "contractuser", "password": "rahasia123", "profile": make_profile()},
    )
    assert r.status_code == 201
    headers = login_as(client, "contractuser")
    assert isinstance(headers, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())