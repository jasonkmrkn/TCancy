from app import consent

URL = "/api/v1"


def test_consent_texts_are_public(client):
    r = client.get("%s/consent-texts" % URL)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "v2"
    assert list(body["scopes"]) == ["profile", "cv", "video", "identity"]
    assert body["scopes"] == consent.TEXTS
    assert body["scopes"]["cv"] == "Allow the job owner to open my CV."