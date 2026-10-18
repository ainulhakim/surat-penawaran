from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User, Wilayah
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MeResponse, TokenResponse
from app.services.audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun tidak aktif")
    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, user, "LOGIN", "users", user.id)
    db.commit()
    token = create_access_token(user.id, {"role": user.role, "wilayah_id": user.wilayah_id})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    wilayah = db.get(Wilayah, user.wilayah_id) if user.wilayah_id else None
    return MeResponse(
        id=user.id,
        nama=user.nama,
        email=user.email,
        role=user.role,
        wilayah_id=user.wilayah_id,
        wilayah_nama=wilayah.nama if wilayah else None,
        has_ttd=bool(user.ttd_image_path),
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password lama salah")
    user.password_hash = hash_password(payload.new_password)
    log_action(db, user, "CHANGE_PASSWORD", "users", user.id)
    db.commit()
    return {"detail": "Password berhasil diubah"}
