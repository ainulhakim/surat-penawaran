from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models import User, UserRole, Wilayah
from app.schemas.wilayah import WilayahCreate, WilayahOut, WilayahUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/wilayah", tags=["wilayah"])

PUSAT = Depends(require_roles(UserRole.SUPERADMIN))


@router.get("", response_model=list[WilayahOut])
def list_wilayah(
    aktif_only: bool = False,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH, UserRole.SPV, UserRole.KEUANGAN)),
    db: Session = Depends(get_db),
) -> list[Wilayah]:
    stmt = select(Wilayah).order_by(Wilayah.nama)
    if aktif_only:
        stmt = stmt.where(Wilayah.is_active.is_(True))
    if UserRole(user.role) != UserRole.SUPERADMIN:
        stmt = stmt.where(Wilayah.id == user.wilayah_id)
    return list(db.scalars(stmt).all())


@router.post("", response_model=WilayahOut, status_code=201)
def create_wilayah(
    payload: WilayahCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Wilayah:
    if db.scalar(select(Wilayah).where(Wilayah.kode == payload.kode)):
        raise HTTPException(status_code=409, detail="Kode wilayah sudah dipakai")
    wilayah = Wilayah(**payload.model_dump())
    db.add(wilayah)
    db.flush()
    log_action(db, user, "CREATE", "wilayah", wilayah.id, payload.model_dump_json())
    db.commit()
    db.refresh(wilayah)
    return wilayah


@router.patch("/{wilayah_id}", response_model=WilayahOut)
def update_wilayah(
    wilayah_id: int,
    payload: WilayahUpdate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Wilayah:
    wilayah = db.get(Wilayah, wilayah_id)
    if not wilayah:
        raise HTTPException(status_code=404, detail="Wilayah tidak ditemukan")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(wilayah, field, value)
    log_action(db, user, "UPDATE", "wilayah", wilayah_id, payload.model_dump_json(exclude_unset=True))
    db.commit()
    db.refresh(wilayah)
    return wilayah


@router.delete("/{wilayah_id}")
def delete_wilayah(
    wilayah_id: int,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    wilayah = db.get(Wilayah, wilayah_id)
    if not wilayah:
        raise HTTPException(status_code=404, detail="Wilayah tidak ditemukan")
    wilayah.is_active = False
    log_action(db, user, "DEACTIVATE", "wilayah", wilayah_id)
    db.commit()
    return {"detail": f"Wilayah {wilayah.nama} dinonaktifkan"}
