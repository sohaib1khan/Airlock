"""Derive public browser URL / WebAuthn / cookie settings from reverse-proxy headers."""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.requests import Request

from config import Settings


def _first_csv(value: str) -> str:
    return value.split(",")[0].strip()


def public_origin(request: Request, settings: Settings) -> str | None:
    """Browser-facing origin (scheme + host[:port]) e.g. https://vdi.example.com."""
    if settings.trust_forwarded_headers:
        fwd_host = request.headers.get("x-forwarded-host")
        host = _first_csv(fwd_host) if fwd_host else ""
        if not host:
            host = _first_csv(request.headers.get("host") or "")
        if not host:
            return None
        fwd_proto = request.headers.get("x-forwarded-proto")
        proto = (_first_csv(fwd_proto) if fwd_proto else request.url.scheme).lower()
        return f"{proto}://{host}"

    # Direct access (no trusted proxy): use the URL the ASGI server saw.
    host = request.url.hostname
    if not host:
        return None
    scheme = (request.url.scheme or "http").lower()
    port = request.url.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def webauthn_origin_for_request(request: Request, settings: Settings) -> str:
    po = public_origin(request, settings)
    if po:
        return po
    return settings.webauthn_origin


def webauthn_rp_id_for_request(request: Request, settings: Settings) -> str:
    po = public_origin(request, settings)
    if po:
        try:
            host = urlparse(po).hostname
            if host:
                return host.lower()
        except Exception:
            pass
    return settings.webauthn_rp_id


def cookie_secure_for_request(request: Request, settings: Settings) -> bool:
    if settings.cookie_secure:
        return True
    if settings.trust_forwarded_headers:
        proto = _first_csv(request.headers.get("x-forwarded-proto") or "").lower()
        if proto == "https":
            return True
        po = public_origin(request, settings)
        if po and po.startswith("https://"):
            return True
    return False


def cors_allowed_origins(request: Request, settings: Settings) -> set[str]:
    """Origins allowed for CORS (credentials), including auto-detected public origin."""
    out = {o.strip() for o in settings.allowed_origins.split(",") if o.strip()}
    po = public_origin(request, settings)
    if po:
        out.add(po)
    if settings.app_env == "development":
        out.update(
            {
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:32770",
                "http://127.0.0.1:32770",
            }
        )
    return out
