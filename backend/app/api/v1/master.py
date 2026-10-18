from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Bidang, Kategori, Objek, User, UserRole
from app.schemas.master import BidangCreate, BidangOut, KategoriCreate, KategoriOut, ObjekCreate, ObjekOut
from app.services.audit import log_action

router = APIRouter(prefix="/master", tags=["master"])
PUSAT = require_roles(UserRole.SUPERADMIN)


@router.get("/kategori", response_model=list[KategoriOut])
def list_kategori(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Kategori]:
    return list(db.scalars(select(Kategori).order_by(Kategori.nama)).all())


@router.post("/kategori", response_model=KategoriOut, status_code=201)
def create_kategori(
    payload: KategoriCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Kategori:
    if db.scalar(select(Kategori).where(Kategori.kode == payload.kode)):
        raise HTTPException(status_code=409, detail="Kode kategori sudah ada")
    obj = Kategori(**payload.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user, "CREATE", "kategori", obj.id, obj.nama)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/bidang", response_model=list[BidangOut])
def list_bidang(
    kategori_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Bidang]:
    stmt = select(Bidang).order_by(Bidang.nama)
    if kategori_id:
        stmt = stmt.where(Bidang.kategori_id == kategori_id)
    return list(db.scalars(stmt).all())


@router.post("/bidang", response_model=BidangOut, status_code=201)
def create_bidang(
    payload: BidangCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Bidang:
    if not db.get(Kategori, payload.kategori_id):
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    obj = Bidang(**payload.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user, "CREATE", "bidang", obj.id, obj.nama)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/objek", response_model=list[ObjekOut])
def list_objek(
    bidang_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Objek]:
    stmt = select(Objek).order_by(Objek.nama)
    if bidang_id:
        stmt = stmt.where(Objek.bidang_id == bidang_id)
    return list(db.scalars(stmt).all())


@router.post("/objek", response_model=ObjekOut, status_code=201)
def create_objek(
    payload: ObjekCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Objek:
    if not db.get(Bidang, payload.bidang_id):
        raise HTTPException(status_code=404, detail="Bidang tidak ditemukan")
    obj = Objek(**payload.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user, "CREATE", "objek", obj.id, obj.nama)
    db.commit()
    db.refresh(obj)
    return obj
