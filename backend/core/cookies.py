from fastapi import Request, Response

from config import Settings
from core.public_url import cookie_secure_for_request


def set_refresh_cookie(
    response: Response, token: str, settings: Settings, request: Request | None = None
) -> None:
    secure = cookie_secure_for_request(request, settings) if request is not None else settings.cookie_secure
    kwargs: dict = {
        "key": "refresh_token",
        "value": token,
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
        "max_age": int(settings.refresh_token_expire_hours * 3600),
        "path": "/",
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.set_cookie(**kwargs)


def clear_refresh_cookie(response: Response, settings: Settings, request: Request | None = None) -> None:
    secure = cookie_secure_for_request(request, settings) if request is not None else settings.cookie_secure
    kwargs: dict = {
        "key": "refresh_token",
        "path": "/",
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.delete_cookie(**kwargs)
