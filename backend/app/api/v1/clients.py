from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Client, User, UserRole
from app.schemas.client import ClientCreate, ClientOut, ClientPublicOut, ClientUpdate
from app.services.audit import log_action
from app.services.locks import active_lock

router = APIRouter(prefix="/clients", tags=["clients"])


def _lock_info(db: Session, client_id: int) -> tuple[str, str | None]:
    lock = active_lock(db, client_id)
    if not lock:
        return "FREE", None
    return "LOCKED", lock.expires_at.isoformat()


def _to_out(db: Session, client: Client, viewer: User) -> ClientOut:
    out = ClientOut.model_validate(client)
    status, until = _lock_info(db, client.id)
    out.lock_status = status
    out.lock_until = until
    return out


@router.get("", response_model=list[ClientOut])
def list_clients(
    q: str | None = None,
    kota: str | None = None,
    provinsi: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_roles(*list(UserRole))),
    db: Session = Depends(get_db),
) -> list[ClientOut]:
    stmt = select(Client).where(Client.is_active.is_(True)).order_by(Client.nama_perusahaan)
    if UserRole(user.role) != UserRole.SUPERADMIN:
        stmt = stmt.where(Client.wilayah_id == user.wilayah_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Client.nama_perusahaan).like(like),
                func.lower(Client.email).like(like),
                func.lower(Client.pic).like(like),
            )
        )
    if kota:
        stmt = stmt.where(func.lower(Client.kota) == kota.lower())
    if provinsi:
        stmt = stmt.where(func.lower(Client.provinsi) == provinsi.lower())
    stmt = stmt.offset((page - 1) * size).limit(size)
    return [_to_out(db, c, user) for c in db.scalars(stmt).all()]


@router.get("/publik", response_model=list[ClientPublicOut])
def list_publik(
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClientPublicOut]:
    stmt = select(Client).where(Client.is_active.is_(True)).order_by(Client.nama_perusahaan).limit(300)
    if q:
        stmt = stmt.where(func.lower(Client.nama_perusahaan).like(f"%{q.lower()}%"))
    result = []
    for client in db.scalars(stmt).all():
        status, _ = _lock_info(db, client.id)
        result.append(
            ClientPublicOut(
                id=client.id,
                nama_perusahaan=client.nama_perusahaan,
                kota=client.kota,
                provinsi=client.provinsi,
                lock_status=status,
            )
        )
    return result


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    user: User = Depends(require_roles(*list(UserRole))),
    db: Session = Depends(get_db),
) -> ClientOut:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan")
    return _to_out(db, client, user)


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> ClientOut:
    duplicate = db.scalar(
        select(Client).where(
            func.lower(Client.nama_perusahaan) == payload.nama_perusahaan.lower(),
            func.lower(Client.email) == (payload.email or "").lower(),
            func.lower(Client.kota) == (payload.kota or "").lower(),
            Client.kodepos == (payload.kodepos or ""),
            Client.is_active.is_(True),
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"Client sudah terdaftar (nama+email+kota+kodepos sama) dengan ID {duplicate.id}",
        )
    client = Client(**payload.model_dump(), wilayah_id=user.wilayah_id, created_by=user.id)
    db.add(client)
    db.flush()
    log_action(db, user, "CREATE", "clients", client.id, client.nama_perusahaan)
    db.commit()
    db.refresh(client)
    return _to_out(db, client, user)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> ClientOut:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan")
    if UserRole(user.role) != UserRole.SUPERADMIN:
        lock = active_lock(db, client_id)
        if lock and lock.wilayah_id != user.wilayah_id:
            raise HTTPException(status_code=403, detail="Client sedang terkunci wilayah lain")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    log_action(db, user, "UPDATE", "clients", client_id)
    db.commit()
    db.refresh(client)
    return _to_out(db, client, user)


@router.delete("/{client_id}")
def delete_client(
    client_id: int,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> dict:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan")
    if UserRole(user.role) != UserRole.SUPERADMIN and client.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Tidak boleh menghapus client wilayah lain")
    client.is_active = False
    log_action(db, user, "DEACTIVATE", "clients", client_id)
    db.commit()
    return {"detail": "Client dinonaktifkan"}
