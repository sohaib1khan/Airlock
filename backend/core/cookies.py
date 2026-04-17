from fastapi import Response

from config import Settings


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    kwargs: dict = {
        "key": "refresh_token",
        "value": token,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "strict",
        "max_age": int(settings.refresh_token_expire_hours * 3600),
        "path": "/",
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.set_cookie(**kwargs)


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    kwargs: dict = {
        "key": "refresh_token",
        "path": "/",
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "strict",
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    response.delete_cookie(**kwargs)
