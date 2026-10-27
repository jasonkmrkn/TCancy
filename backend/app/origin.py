from app.csrf import SAFE_METHODS
from app.middleware import send_json


class OriginCheckMiddleware:
    def __init__(self, app, allowed_origin: str):
        self.app = app
        self.allowed = allowed_origin.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            origins = [v for k, v in scope["headers"] if k == b"origin"]
            if any(v != self.allowed for v in origins):
                await send_json(send, 403, "CSRF_FAILED")
                return
        await self.app(scope, receive, send)