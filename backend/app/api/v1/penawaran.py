from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.deps import get_current_user, is_pusat, require_roles
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalLog,
    Client,
    Penawaran,
    PenawaranItem,
    PenawaranStatus,
    User,
    UserRole,
    Wilayah,
)
from app.schemas.penawaran import ApprovalIn, DealIn, PenawaranCreate, PenawaranOut, PenawaranRingkas, PenawaranUpdate
from app.services import locks, notify
from app.services.audit import log_action
from app.services.files import save_base64_image
from app.services.numbering import next_penawaran_number

router = APIRouter(prefix="/penawaran", tags=["penawaran"])

EDITABLE = {PenawaranStatus.DRAFT, PenawaranStatus.REVISI}


def _compute_total(items: list[PenawaranItem]) -> Decimal:
    total = Decimal("0")
    for item in items:
        harga = item.harga_nego if (item.is_nego and item.harga_nego is not None) else item.harga_satuan
        item.subtotal = (item.qty or Decimal("0")) * (harga or Decimal("0"))
        total += item.subtotal
    return total


def _get_or_404(db: Session, penawaran_id: int) -> Penawaran:
    obj = db.scalar(
        select(Penawaran).options(selectinload(Penawaran.items)).where(Penawaran.id == penawaran_id)
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Penawaran tidak ditemukan")
    return obj


def _assert_rahasia_access(db: Session, penawaran: Penawaran, user: User) -> None:
    if is_pusat(user):
        return
    if penawaran.wilayah_id != user.wilayah_id:
        raise HTTPException(
            status_code=403,
            detail="Penawaran bersifat rahasia: hanya wilayah pembuat dan Pusat yang dapat melihat detail",
        )


@router.get("", response_model=list[PenawaranRingkas])
def list_penawaran(
    status: PenawaranStatus | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PenawaranRingkas]:
    stmt = (
        select(Penawaran, Client)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(Penawaran.created_at.desc())
        .limit(200)
    )
    if not is_pusat(user):
        stmt = stmt.where(Penawaran.wilayah_id == user.wilayah_id)
    if status is not None:
        stmt = stmt.where(Penawaran.status == status)
    result = []
    for penawaran, client in db.execute(stmt).all():
        result.append(
            PenawaranRingkas(
                id=penawaran.id,
                nomor_surat=penawaran.nomor_surat,
                status=penawaran.status,
                perihal=penawaran.perihal,
                nama_perusahaan=client.nama_perusahaan,
                kota=client.kota,
                harga_total=penawaran.harga_total,
                valid_until=penawaran.valid_until,
                is_nego=penawaran.is_nego,
            )
        )
    return result


@router.get("/publik", response_model=list[PenawaranRingkas])
def list_publik_penawaran(
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PenawaranRingkas]:
    stmt = (
        select(Penawaran, Client)
        .join(Client, Client.id == Penawaran.client_id)
        .where(Penawaran.status.notin_([PenawaranStatus.BATAL, PenawaranStatus.DRAFT, PenawaranStatus.REVISI]))
        .order_by(Penawaran.approved_at.desc())
        .limit(200)
    )
    if q:
        stmt = stmt.where(func.lower(Client.nama_perusahaan).like(f"%{q.lower()}%"))
    result = []
    for penawaran, client in db.execute(stmt).all():
        result.append(
            PenawaranRingkas(
                id=penawaran.id,
                nomor_surat="",
                status=penawaran.status,
                perihal="",
                nama_perusahaan=client.nama_perusahaan,
                kota=client.kota,
                harga_total=None,
                valid_until=penawaran.valid_until,
                is_nego=False,
            )
        )
    return result


@router.get("/{penawaran_id}", response_model=PenawaranOut)
def get_penawaran(
    penawaran_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Penawaran:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    return penawaran


@router.post("", response_model=PenawaranOut, status_code=201)
def create_penawaran(
    payload: PenawaranCreate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> Penawaran:
    if not is_pusat(user) and user.wilayah_id is None:
        raise HTTPException(status_code=403, detail="User tidak terikat wilayah")

    client = db.get(Client, payload.client_id)
    if not client or not client.is_active:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan / tidak aktif")

    lock = locks.active_lock(db, client.id)
    if lock and (is_pusat(user) or lock.wilayah_id != user.wilayah_id):
        wilayah = db.get(Wilayah, lock.wilayah_id)
        raise HTTPException(
            status_code=409,
            detail=f"Client sedang dalam proses penawaran wilayah {wilayah.nama if wilayah else lock.wilayah_id} "
                   f"sampai {lock.expires_at:%d-%m-%Y %H:%M} UTC",
        )

    wilayah_id = user.wilayah_id if not is_pusat(user) else client.wilayah_id
    if wilayah_id is None:
        raise HTTPException(status_code=400, detail="Tentukan wilayah penawaran")
    wilayah = db.get(Wilayah, wilayah_id)
    urut, tahun, nomor = next_penawaran_number(db, wilayah)

    penawaran = Penawaran(
        nomor_surat=nomor,
        nomor_urut=urut,
        tahun=tahun,
        client_id=client.id,
        wilayah_id=wilayah_id,
        admin_id=user.id,
        perihal=payload.perihal or f"Penawaran untuk {client.nama_perusahaan}",
        catatan=payload.catatan,
        is_nego=payload.is_nego,
        status=PenawaranStatus.DRAFT,
    )
    for item in payload.items:
        penawaran.items.append(PenawaranItem(**item.model_dump()))
    penawaran.harga_total = _compute_total(penawaran.items)
    db.add(penawaran)
    db.flush()
    log_action(db, user, "CREATE", "penawaran", penawaran.id, nomor)
    db.commit()
    db.refresh(penawaran)
    return penawaran


@router.patch("/{penawaran_id}", response_model=PenawaranOut)
def update_penawaran(
    penawaran_id: int,
    payload: PenawaranUpdate,
    user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN_WILAYAH)),
    db: Session = Depends(get_db),
) -> Penawaran:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    if PenawaranStatus(penawaran.status) not in EDITABLE:
        raise HTTPException(status_code=400, detail=f"Penawaran berstatus {penawaran.status} tidak dapat diubah")
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)
    for field, value in data.items():
        setattr(penawaran, field, value)
    if items is not None:
        penawaran.items.clear()
        db.flush()
        for item in items:
            penawaran.items.append(PenawaranItem(**item))
    penawaran.harga_total = _compute_total(penawaran.items)
    log_action(db, user, "UPDATE", "penawaran", penawaran.id)
    db.commit()
    db.refresh(penawaran)
    return penawaran


@router.post("/{penawaran_id}/submit", response_model=PenawaranOut)
def submit_penawaran(
    penawaran_id: int,
    user: User = Depends(require_roles(UserRole.ADMIN_WILAYAH, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Penawaran:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    if PenawaranStatus(penawaran.status) not in EDITABLE:
        raise HTTPException(status_code=400, detail="Hanya draft/revisi yang dapat diajukan")
    if not penawaran.items:
        raise HTTPException(status_code=400, detail="Penawaran belum memiliki item")
    penawaran.harga_total = _compute_total(penawaran.items)
    penawaran.status = PenawaranStatus.MENUNGGU_SPV
    log_action(db, user, "SUBMIT", "penawaran", penawaran.id)
    db.commit()
    db.refresh(penawaran)

    client = db.get(Client, penawaran.client_id)
    notif.notify(
        db,
        f"📄 *Penawaran menunggu approval*\n"
        f"No: {penawaran.nomor_surat}\nClient: {client.nama_perusahaan} ({client.kota})\n"
        f"Nilai: Rp{penawaran.harga_total:,.0f}\n"
        f"Nego: {'YA' if penawaran.is_nego else 'tidak'}\n"
        f"Wilayah: {penawaran.wilayah_id} — silakan buka aplikasi untuk Approve/Revisi.",
        "SPV_APPROVAL",
        penawaran.wilayah_id,
        roles=(UserRole.SPV,),
    )
    return penawaran


@router.post("/{penawaran_id}/approval", response_model=PenawaranOut)
def approval_penawaran(
    penawaran_id: int,
    payload: ApprovalIn,
    user: User = Depends(require_roles(UserRole.SPV, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Penawaran:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    if PenawaranStatus(penawaran.status) != PenawaranStatus.MENUNGGU_SPV:
        raise HTTPException(status_code=400, detail="Penawaran tidak dalam status menunggu approval")

    aksi_raw = (payload.aksi or "").upper()
    if aksi_raw not in {ApprovalAction.APPROVE, ApprovalAction.REVISI}:
        raise HTTPException(status_code=400, detail="Aksi harus APPROVE atau REVISI")

    ttd_path = None
    if aksi_raw == ApprovalAction.APPROVE:
        ttd_path = save_base64_image(payload.ttd_image_base64 or "", "ttd", f"spv{user.id}") or user.ttd_image_path
        if not ttd_path:
            raise HTTPException(status_code=400, detail="Tanda tangan digital wajib dikirim untuk Approve")
        if not user.ttd_image_path:
            user.ttd_image_path = ttd_path
        days = settings.LOCK_DAYS_NEGO if penawaran.is_nego else settings.LOCK_DAYS_NORMAL
        penawaran.status = PenawaranStatus.APPROVED
        penawaran.approved_by = user.id
        penawaran.approved_at = datetime.now(timezone.utc)
        penawaran.ttd_spv_path = ttd_path
        penawaran.valid_until = date.today() + timedelta(days=days)
        if not locks.active_lock(db, penawaran.client_id):
            locks.create_lock(
                db,
                client_id=penawaran.client_id,
                penawaran_id=penawaran.id,
                wilayah_id=penawaran.wilayah_id,
                user_id=user.id,
                nego=penawaran.is_nego,
            )
    else:
        if not (payload.catatan or "").strip():
            raise HTTPException(status_code=400, detail="Catatan revisi wajib diisi")
        penawaran.status = PenawaranStatus.REVISI
        penawaran.revisi_catatan = payload.catatan

    db.add(
        ApprovalLog(
            penawaran_id=penawaran.id,
            spv_id=user.id,
            aksi=aksi_raw,
            catatan=payload.catatan,
            ttd_path=ttd_path,
        )
    )
    log_action(db, user, aksi_raw, "penawaran", penawaran.id)
    db.commit()
    db.refresh(penawaran)

    if aksi_raw == ApprovalAction.APPROVE:
        notif.notify(
            db,
            f"✅ *Penawaran disetujui*\nNo: {penawaran.nomor_surat}\n"
            f"Berlaku sampai: {penawaran.valid_until}\n"
            f"Durasi: {settings.LOCK_DAYS_NEGO if penawaran.is_nego else settings.LOCK_DAYS_NORMAL} hari "
            f"({'NEGO' if penawaran.is_nego else 'normal'})\n"
            f"Client terkunci untuk wilayah lain selama masa berlaku.",
            "ADMIN_GRUP",
            penawaran.wilayah_id,
            roles=(UserRole.ADMIN_WILAYAH,),
        )
    else:
        notif.notify(
            db,
            f"♻️ *Penawaran perlu revisi*\nNo: {penawaran.nomor_surat}\nCatatan SPV: {payload.catatan}",
            "ADMIN_GRUP",
            penawaran.wilayah_id,
            roles=(UserRole.ADMIN_WILAYAH,),
        )
    return penawaran


@router.post("/{penawaran_id}/deal", response_model=PenawaranOut)
def deal_penawaran(
    penawaran_id: int,
    payload: DealIn,
    user: User = Depends(require_roles(UserRole.ADMIN_WILAYAH, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> Penawaran:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    if PenawaranStatus(penawaran.status) != PenawaranStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Hanya penawaran APPROVED yang dapat di-input PO/SPK")
    penawaran.tgl_po = payload.tgl_po
    penawaran.no_spk = payload.no_spk
    if payload.nilai_po is not None:
        penawaran.nilai_po = payload.nilai_po
    penawaran.status = PenawaranStatus.DEAL
    log_action(db, user, "DEAL", "penawaran", penawaran.id, f"PO={payload.tgl_po} SPK={payload.no_spk}")
    db.commit()
    db.refresh(penawaran)

    client = db.get(Client, penawaran.client_id)
    notif.notify(
        db,
        f"🤝 *DEAL* — {client.nama_perusahaan}\nNo penawaran: {penawaran.nomor_surat}\n"
        f"Tgl PO: {payload.tgl_po}\nNo SPK: {payload.no_spk}\nSilakan lanjut booking PIC.",
        "ADMIN_GRUP",
        penawaran.wilayah_id,
        roles=(UserRole.ADMIN_WILAYAH,),
    )
    return penawaran


@router.get("/{penawaran_id}/riwayat")
def riwayat_penawaran(
    penawaran_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    penawaran = _get_or_404(db, penawaran_id)
    _assert_rahasia_access(db, penawaran, user)
    logs = db.scalars(
        select(ApprovalLog).where(ApprovalLog.penawaran_id == penawaran_id).order_by(ApprovalLog.created_at)
    ).all()
    user_map = {u.id: u.nama for u in db.scalars(select(User)).all()}
    return [
        {
            "aksi": log.aksi,
            "catatan": log.catatan,
            "oleh": user_map.get(log.spv_id, "-"),
            "waktu": log.created_at.isoformat() if log.created_at else None,
            "ttd_path": log.ttd_path,
        }
        for log in logs
    ]
