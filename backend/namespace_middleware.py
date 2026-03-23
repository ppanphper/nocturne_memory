"""
ASGI middleware for namespace extraction.

Shared by both the SSE/Streamable HTTP entry point (run_sse.py)
and the REST API entry point (main.py).
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from db.namespace import set_namespace


class NamespaceMiddleware:
    """ASGI middleware that extracts the namespace from request headers/query.

    Priority: ``X-Namespace`` header > ``namespace`` query parameter > default "".
    The value is written into the contextvars-based namespace context so that
    all downstream Path / SearchDocument queries are automatically scoped.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        ns = request.headers.get("x-namespace", "")
        if not ns:
            ns = request.query_params.get("namespace", "")

        set_namespace(ns)
        await self.app(scope, receive, send)
