from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User, UserRole
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/users", tags=["users"])


def _to_out(user: User) -> UserOut:
    data = UserOut.model_validate(user)
    data.has_ttd = bool(user.ttd_image_path)
    return data


@router.get("", response_model=list[UserOut])
def list_users(
    role: UserRole | None = None,
    wilayah_id: int | None = None,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    stmt = select(User).order_by(User.nama)
    if UserRole(user.role) != UserRole.SUPERADMIN:
        stmt = stmt.where(User.wilayah_id == user.wilayah_id)
    elif wilayah_id is not None:
        stmt = stmt.where(User.wilayah_id == wilayah_id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    return [_to_out(u) for u in db.scalars(stmt).all()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> UserOut:
    if UserRole(user.role) != UserRole.SUPERADMIN:
        if payload.role == UserRole.SUPERADMIN:
            raise HTTPException(status_code=403, detail="Hanya Pusat yang boleh membuat SuperAdmin")
        payload.wilayah_id = user.wilayah_id
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email sudah terdaftar")
    data = payload.model_dump()
    password = data.pop("password")
    data["email"] = payload.email.lower()
    new_user = User(**data, password_hash=hash_password(password))
    db.add(new_user)
    db.flush()
    log_action(db, user, "CREATE", "users", new_user.id, f"role={new_user.role} wilayah={new_user.wilayah_id}")
    db.commit()
    db.refresh(new_user)
    return _to_out(new_user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> UserOut:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if UserRole(actor.role) != UserRole.SUPERADMIN and target.wilayah_id != actor.wilayah_id:
        raise HTTPException(status_code=403, detail="Tidak boleh mengubah user wilayah lain")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(target, field, value)
    if password:
        target.password_hash = hash_password(password)
    log_action(db, actor, "UPDATE", "users", user_id)
    db.commit()
    db.refresh(target)
    return _to_out(target)


@router.post("/me/ttd")
def upload_ttd(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.files import save_base64_image

    path = save_base64_image(payload.get("image_base64", ""), "ttd", f"user{user.id}")
    if not path:
        raise HTTPException(status_code=400, detail="Gambar tanda tangan tidak valid")
    user.ttd_image_path = path
    log_action(db, user, "UPLOAD_TTD", "users", user.id)
    db.commit()
    return {"detail": "Tanda tangan tersimpan", "path": path}
