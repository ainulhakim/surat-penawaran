from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token tidak valid atau kadaluarsa",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise CREDENTIALS_ERROR
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        raise CREDENTIALS_ERROR
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    def _checker(user: User = Depends(get_current_user)) -> User:
        if UserRole(user.role) not in allowed:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk role ini")
        return user

    return _checker


def is_pusat(user: User) -> bool:
    return UserRole(user.role) == UserRole.SUPERADMIN


def resolve_wilayah_scope(user: User, wilayah_id: int | None = None) -> int | None:
    role = UserRole(user.role)
    if role == UserRole.SUPERADMIN:
        return wilayah_id
    if user.wilayah_id is None:
        raise HTTPException(status_code=403, detail="User tidak terikat wilayah")
    if wilayah_id is not None and wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Tidak boleh mengakses data wilayah lain")
    return user.wilayah_id


def assert_wilayah_access(user: User, target_wilayah_id: int | None) -> None:
    if is_pusat(user):
        return
    if target_wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Tidak boleh mengakses data wilayah lain")
