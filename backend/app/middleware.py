"""Bound multipart request bytes before FastAPI can spool an oversized upload to disk."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitExceeded(Exception):
    """Interrupt request parsing when streamed bytes exceed the upload budget."""


class UploadLimitMiddleware:
    """Enforce an upload envelope limit even when a client omits Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        """Allow a small multipart overhead above the stricter per-file size check."""
        self.app, self.max_bytes = app, max_bytes + 65536

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Count upload bytes and substitute a consistent 413 response on overflow."""
        if scope["type"] != "http" or scope["path"] != "/api/documents/upload":
            await self.app(scope, receive, send)
            return
        total, exceeded = 0, False
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "upload_too_large",
                    "message": "Upload exceeds MAX_UPLOAD_MB. Use a smaller file.",
                }
            },
        )

        async def limited_receive() -> Message:
            """Stop an over-budget stream before the multipart parser receives more bytes."""
            nonlocal total, exceeded
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                exceeded = True
                raise BodyLimitExceeded()
            return message

        async def limited_send(message: Message) -> None:
            """Suppress parser errors when a more informative 413 must be returned."""
            if not exceeded:
                await send(message)

        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > self.max_bytes:
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, limited_receive, limited_send)
        except BodyLimitExceeded:
            exceeded = True
        if exceeded:
            await response(scope, receive, send)
