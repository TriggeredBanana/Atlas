"""
Internal authentication for MCP server endpoints.

All MCP endpoints (/mcp/*) must only be called by the server-side session
manager, never directly by external clients.  A per-process secret token is
generated at startup and required in the X-MCP-Internal-Token header on every
incoming HTTP request.  Requests missing or carrying an incorrect token receive
a 401 response before the MCP handler ever runs.

Usage:
  # server.py
  from mcp_auth import MCPAuthMiddleware, MCP_INTERNAL_SECRET
  Mount("/mcp/map", app=MCPAuthMiddleware(map_app))

  # session_manager.py
  from mcp_auth import MCP_INTERNAL_SECRET
  "headers": {"X-MCP-Internal-Token": MCP_INTERNAL_SECRET}
"""

import secrets

# Generated once per server process.  Session manager embeds this value in
# the Authorization header when it registers MCP server URLs with the Copilot
# SDK, so only in-process calls succeed.
MCP_INTERNAL_SECRET: str = secrets.token_urlsafe(32)

_HEADER_NAME: bytes = b"x-mcp-internal-token"
_EXPECTED: bytes = MCP_INTERNAL_SECRET.encode()


class MCPAuthMiddleware:
    """
    Lightweight ASGI middleware that guards MCP HTTP endpoints.

    Non-HTTP scopes (lifespan, websocket) are forwarded unchanged so that
    FastMCP startup/shutdown and any future transport upgrades still work.
    """

    __slots__ = ("_app",)

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers: dict[bytes, bytes] = dict(scope.get("headers", []))
            token: bytes = headers.get(_HEADER_NAME, b"")
            if not secrets.compare_digest(token, _EXPECTED):
                await _reject_401(send)
                return

        await self._app(scope, receive, send)


async def _reject_401(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"error":"Unauthorized"}',
            "more_body": False,
        }
    )
