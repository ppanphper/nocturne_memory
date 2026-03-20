import os
import sys
import uvicorn

# Ensure we can import from backend dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth import BearerTokenAuthMiddleware
from db.namespace import set_namespace
from mcp_server import mcp

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


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


def main():
    """
    Run the Nocturne Memory MCP server using SSE (Server-Sent Events) transport.
    This is required for clients that don't support stdio (like some web-based tools).
    """
    print("Initializing Nocturne Memory SSE Server...")

    # For legacy SSE clients (like some older UI tools or Claude Desktop)
    # This exposes GET /sse and POST /messages/
    sse_asgi_app = mcp.sse_app("/")

    # For newer Streamable HTTP clients (like GitHub Copilot type: "http")
    # This exposes GET/POST on /mcp
    streamable_asgi_app = mcp.streamable_http_app()

    # Combine routes into one ASGI app
    from starlette.applications import Starlette
    import contextlib

    @contextlib.asynccontextmanager
    async def combined_lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(sse_asgi_app.router.lifespan_context(app))
            await stack.enter_async_context(streamable_asgi_app.router.lifespan_context(app))
            yield

    routes = []
    routes.extend(sse_asgi_app.router.routes)
    routes.extend(streamable_asgi_app.router.routes)
    combined_app = Starlette(routes=routes, lifespan=combined_lifespan)

    app = NamespaceMiddleware(BearerTokenAuthMiddleware(combined_app, excluded_paths=[]))

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting SSE Server on http://{host}:{port}")
    print(f"Legacy SSE Endpoint: http://{host}:{port}/sse")
    print(f"Streamable HTTP Endpoint: http://{host}:{port}/mcp")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
