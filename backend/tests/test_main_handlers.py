from app.main import app
from app.ratelimit import RateLimitUnavailable


def test_rate_limit_unavailable_returns_503(client):
    def boom():
        raise RateLimitUnavailable()

    app.add_api_route("/__test/rate-limit-unavailable", boom)
    route = app.router.routes[-1]
    try:
        r = client.get("/__test/rate-limit-unavailable")
    finally:
        app.router.routes.remove(route)

    assert r.status_code == 503
    assert r.json() == {"detail": "RATE_LIMIT_UNAVAILABLE"}
