"""Sesi UI berbasis cookie HttpOnly — memakai ulang JWT dari app.core.security."""

from fastapi import Request, Response

from app.core.config import settings
from app.core.security import create_access_token, decode_token

COOKIE_NAME = settings.COOKIE_NAME


def set_session(response: Response, user) -> None:
    """Terbitkan token sesi dan simpan sebagai cookie HttpOnly."""
    token = create_access_token(user.id, {"role": user.role, "wilayah_id": user.wilayah_id})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def user_id_from_request(request: Request) -> int | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        return None
