from __future__ import annotations

import os
import secrets
from typing import Iterable, Sequence

from dotenv import find_dotenv, load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send


# 尽早加载 .env，确保独立导入本模块时也能读取 API_TOKEN。
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path)


UNAUTHORIZED_MESSAGE = {"detail": "Unauthorized"}


def _normalize_path(path: str) -> str:
    if not path or path == "/":
        return "/"
    normalized = f"/{path.lstrip('/')}"
    return normalized.rstrip("/") or "/"


def is_excluded_path(path: str, excluded_paths: Iterable[str] | None = None) -> bool:
    normalized_path = _normalize_path(path)

    for raw_excluded_path in excluded_paths or ():
        excluded_path = _normalize_path(raw_excluded_path)
        if excluded_path == "/":
            return True
        if normalized_path == excluded_path:
            return True
        if normalized_path.startswith(f"{excluded_path}/"):
            return True

    return False


def get_api_token() -> str | None:
    return os.environ.get("API_TOKEN")


def _unauthorized_response() -> JSONResponse:
    return JSONResponse(status_code=401, content=UNAUTHORIZED_MESSAGE)


async def verify_token(
    request: Request,
    expected_token: str | None = None,
) -> Response | None:
    """校验 Bearer Token。

    Args:
        request: Starlette/FastAPI 请求对象。
        expected_token: 可选的预读 token；未传入时会从环境变量读取。

    Returns:
        校验失败时返回 401 JSONResponse，成功时返回 None。
    """

    token = expected_token if expected_token is not None else get_api_token()
    
    # 如果没有设置 token，默认不进行验证
    if not token:
        return None
    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return _unauthorized_response()

    provided_token = authorization.removeprefix("Bearer ").strip()
    if not provided_token:
        return _unauthorized_response()

    if not secrets.compare_digest(provided_token, token):
        return _unauthorized_response()

    return None


class BearerTokenAuthMiddleware:
    """通用 Bearer Token ASGI 中间件。

    设计目标：
    - FastAPI: `app.add_middleware(BearerTokenAuthMiddleware, excluded_paths=[...])`
    - Starlette/ASGI: `app = BearerTokenAuthMiddleware(app, excluded_paths=[...])`
    """

    def __init__(
        self,
        app: ASGIApp,
        excluded_paths: Sequence[str] | None = None,
    ) -> None:
        self.app = app
        self.excluded_paths = tuple(excluded_paths or ())
        self.expected_token = get_api_token()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 如果没有配置 Token，直接放行所有 HTTP 请求
        if not self.expected_token:
            await self.app(scope, receive, send)
            return

        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        if is_excluded_path(path, self.excluded_paths):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        response = await verify_token(request, expected_token=self.expected_token)
        if response is not None:
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def get_cors_config() -> dict:
    """Return kwargs for CORSMiddleware based on CORS_ORIGINS env var.

    - Unset / empty  → regex that matches localhost / 127.0.0.1 on any port
    - "*"            → allow all origins
    - Comma-list     → exact-match those origins
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw == "*":
        return {"allow_origins": ["*"]}
    if raw:
        return {"allow_origins": [o.strip() for o in raw.split(",") if o.strip()]}
    return {"allow_origin_regex": r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"}


def enforce_network_auth(*, host: str = "0.0.0.0") -> None:
    """Refuse to start an HTTP/SSE server without API_TOKEN.

    Raises RuntimeError when API_TOKEN is empty/unset. Call this before
    uvicorn.run() in any network-facing entry point (run_sse.py, main.py).
    """
    token = get_api_token()
    if token and len(token) < 32:
        raise RuntimeError(
            f"API_TOKEN is too short ({len(token)} chars). "
            f"Use at least 32 characters for security."
        )
    if token:
        if host not in ("127.0.0.1", "localhost", "::1"):
            print(
                f"  Auth enabled (HOST={host}). "
                f"MCP clients must send the header:\n"
                f"      Authorization: Bearer <your-API_TOKEN>\n"
                f"  See README for client configuration examples.",
            )
        return
    is_localhost = host in ("127.0.0.1", "localhost", "::1")
    if is_localhost:
        import warnings
        warnings.warn(
            "API_TOKEN is not set. The server is binding to localhost only, "
            "but setting API_TOKEN is still strongly recommended.",
            stacklevel=2,
        )
        return
    raise RuntimeError(
        f"\n\n"
        f"  API_TOKEN is not set, but HOST={host!r} is network-reachable.\n"
        f"\n"
        f"  Fix: add API_TOKEN to your .env file:\n"
        f"\n"
        f"    python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
        f"\n"
        f"  Copy the output into .env as:  API_TOKEN=<paste here>\n"
        f"  Then update your MCP client config to include:\n"
        f"      \"headers\": {{\"Authorization\": \"Bearer <your-API_TOKEN>\"}}\n"
        f"\n"
        f"  Or set HOST=127.0.0.1 to only allow local connections.\n"
    )


__all__ = [
    "BearerTokenAuthMiddleware",
    "UNAUTHORIZED_MESSAGE",
    "enforce_network_auth",
    "get_api_token",
    "get_cors_config",
    "is_excluded_path",
    "verify_token",
]
