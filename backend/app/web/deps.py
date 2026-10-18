"""Dependency & guard untuk halaman HTML (bukan API)."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User, UserRole
from app.web.session import user_id_from_request


class NotAuthenticated(Exception):
    """Belum login → alihkan ke /login."""


class Forbidden(Exception):
    """Sudah login tapi role tidak berhak → 403."""

    def __init__(self, message: str = "Akses ditolak untuk role ini") -> None:
        super().__init__(message)
        self.message = message


def web_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = user_id_from_request(request)
    if uid is None:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        return None
    return user


def web_user(user: User | None = Depends(web_user_optional)) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


def web_roles(*roles: UserRole):
    allowed = {UserRole(r) for r in roles}

    def _checker(user: User = Depends(web_user)) -> User:
        if UserRole(user.role) not in allowed:
            raise Forbidden()
        return user

    return _checker


def is_pusat(user: User) -> bool:
    return UserRole(user.role) == UserRole.SUPERADMIN


# Role yang lazim dipakai di banyak halaman
ADMIN_ROLES = (UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)
ALL_ROLES = (
    UserRole.SUPERADMIN,
    UserRole.ADMIN_WILAYAH,
    UserRole.SPV,
    UserRole.PIC,
    UserRole.KEUANGAN,
)
