"""CORS with per-request allowed origins (proxy-detected public URL + configured list)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import get_settings
from core.public_url import cors_allowed_origins


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        origin = request.headers.get("origin")
        allowed = cors_allowed_origins(request, settings)
        origin_ok = bool(origin and origin in allowed)

        if request.method == "OPTIONS":
            headers: dict[str, str] = {}
            if origin_ok and origin:
                headers["access-control-allow-origin"] = origin
                headers["access-control-allow-credentials"] = "true"
            req_method = request.headers.get("access-control-request-method")
            if req_method:
                headers["access-control-allow-methods"] = "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
            req_headers = request.headers.get("access-control-request-headers")
            if req_headers:
                headers["access-control-allow-headers"] = req_headers
            headers["access-control-max-age"] = "600"
            return Response(status_code=204, headers=headers)

        response = await call_next(request)
        if origin_ok and origin:
            response.headers["access-control-allow-origin"] = origin
            response.headers["access-control-allow-credentials"] = "true"
        return response
