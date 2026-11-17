"""Record request outcomes without storing credentials or arbitrary client input."""

from time import perf_counter
from uuid import uuid4


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            services = getattr(scope["app"].state, "services", None)
            if services is not None:
                # Templates avoid storing IDs and secrets from unknown paths.
                route = getattr(scope.get("route"), "path", "unmatched")
                await services.journal.record(
                    "http_request", request_id=request_id, method=scope["method"],
                    route=route, status=status,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
