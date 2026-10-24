"""Pure-ASGI middleware: request-body size limit and security headers."""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body


class BodySizeLimitMiddleware:
    """Rejects request bodies above ``max_bytes`` on the given paths.

    Checks ``Content-Length`` up front, then counts streamed bytes for chunked uploads.
    The streamed check is needed because the multipart parser would otherwise spool an
    unbounded body to disk before the route handler runs.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, paths: set[str]) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.paths = paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = 0
                if declared > self.max_bytes:
                    await _send_too_large(send)
                    return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                # Replace whatever error the framework produced with a clear 413.
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await _send_too_large(send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _send_too_large(send: Send) -> None:
    body = json.dumps(error_body("upload_too_large", "The upload exceeds the maximum archive size.")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


class SecurityHeadersMiddleware:
    """Adds hardening headers. The CSP allows no third-party origins: the bundled UI loads nothing external.

    ``exempt_prefixes`` skips the CSP for the development-only Swagger page, which loads from a CDN.
    """

    def __init__(self, app: ASGIApp, *, exempt_prefixes: tuple[str, ...] = ()) -> None:
        self.app = app
        self.exempt_prefixes = exempt_prefixes
        self.base_headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-frame-options", b"DENY"),
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = list(self.base_headers)
        if not scope["path"].startswith(self.exempt_prefixes):
            headers.append((b"content-security-policy", _CSP.encode()))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *headers]
            await send(message)

        await self.app(scope, receive, send_with_headers)
