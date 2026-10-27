import json

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}
_SECURITY_HEADERS_RAW = tuple((k.encode(), v.encode()) for k, v in SECURITY_HEADERS.items())
_SECURITY_NAMES_RAW = frozenset(k for k, _ in _SECURITY_HEADERS_RAW)


def add_security_headers(response) -> None:
    """For a response object built by hand, such as the one from the 500 handler."""
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                kept = [(k, v) for k, v in message.get("headers", ()) if k.lower() not in _SECURITY_NAMES_RAW]
                message["headers"] = kept + list(_SECURITY_HEADERS_RAW)
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def send_json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"connection", b"close"),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass


class _BadContentLength(Exception):
    pass


def _declared_length(scope) -> int | None:
    """The Content-Length of the request: None if absent, _BadContentLength if unusable."""
    values = {v for k, v in scope["headers"] if k == b"content-length"}
    if not values:
        return None
    if len(values) > 1:
        raise _BadContentLength()
    (value,) = values
    if not value.isdigit():
        raise _BadContentLength()
    return int(value)


class BodySizeLimitMiddleware:
    def __init__(self, app, default_limit: int, limits: dict[tuple[str, str], int] | None = None):
        self.app = app
        self.default_limit = default_limit
        self.limits = dict(limits or {})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limits.get((scope["method"], scope["path"]), self.default_limit)
        try:
            declared = _declared_length(scope)
        except _BadContentLength:
            await send_json(send, 400, "INVALID_CONTENT_LENGTH")
            return
        if declared is not None and declared > limit:
            await send_json(send, 413, "REQUEST_TOO_LARGE")
            return

        received = 0
        exceeded = False
        response_started = False  
        rejected = False

        async def counting_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal response_started, rejected
            if exceeded and not response_started:
                if not rejected:
                    rejected = True
                    await send_json(send, 413, "REQUEST_TOO_LARGE")
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not exceeded or response_started:
                raise
        if exceeded and not response_started and not rejected:
            await send_json(send, 413, "REQUEST_TOO_LARGE")