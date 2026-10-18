from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, is_pusat
from app.db.session import get_db
from app.models import (
    Client,
    ClientLock,
    Invoice,
    InvoiceStatus,
    Lhpp,
    Penawaran,
    PenawaranStatus,
    PicBooking,
    User,
    Wilayah,
)
from app.services import locks, notify

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    scope = None if is_pusat(user) else user.wilayah_id
    now = datetime.now(timezone.utc)

    def count_penawaran(*status: PenawaranStatus) -> int:
        stmt = select(func.count(Penawaran.id)).where(Penawaran.status.in_(status))
        if scope is not None:
            stmt = stmt.where(Penawaran.wilayah_id == scope)
        return int(db.scalar(stmt) or 0)

    total_client = select(func.count(Client.id)).where(Client.is_active.is_(True))
    if scope is not None:
        total_client = total_client.where(Client.wilayah_id == scope)

    lock_aktif = select(func.count(ClientLock.id)).where(
        ClientLock.released_at.is_(None), ClientLock.expires_at > now
    )
    if scope is not None:
        lock_aktif = lock_aktif.where(ClientLock.wilayah_id == scope)

    lhpp_pending = select(func.count(Lhpp.id)).where(Lhpp.is_uploaded.is_(False), Lhpp.wajib.is_(True))
    if scope is not None:
        lhpp_pending = lhpp_pending.where(Lhpp.wilayah_id == scope)

    invoice_pending = select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.TERBIT)
    if scope is not None:
        invoice_pending = invoice_pending.where(Invoice.wilayah_id == scope)

    booking_minggu_ini = select(func.count(PicBooking.id)).where(
        PicBooking.tanggal_tugas.between(date.today(), date.today() + timedelta(days=7))
    )
    if scope is not None:
        booking_minggu_ini = booking_minggu_ini.where(PicBooking.wilayah_id == scope)

    data = {
        "role": user.role,
        "wilayah_id": user.wilayah_id,
        "total_client": int(db.scalar(total_client) or 0),
        "penawaran_draft": count_penawaran(PenawaranStatus.DRAFT, PenawaranStatus.REVISI),
        "menunggu_spv": count_penawaran(PenawaranStatus.MENUNGGU_SPV),
        "approved": count_penawaran(PenawaranStatus.APPROVED),
        "deal": count_penawaran(PenawaranStatus.DEAL, PenawaranStatus.BOOKING_PIC, PenawaranStatus.SURAT_TUGAS),
        "pelaksanaan_lhpp": count_penawaran(PenawaranStatus.PELAKSANAAN, PenawaranStatus.LHPP),
        "invoice": count_penawaran(PenawaranStatus.INVOICE),
        "selesai": count_penawaran(PenawaranStatus.SELESAI),
        "client_lock_aktif": int(db.scalar(lock_aktif) or 0),
        "lhpp_belum_upload": int(db.scalar(lhpp_pending) or 0),
        "invoice_belum_faktur": int(db.scalar(invoice_pending) or 0),
        "booking_7_hari": int(db.scalar(booking_minggu_ini) or 0),
    }
    if is_pusat(user):
        data["total_wilayah"] = int(db.scalar(select(func.count(Wilayah.id)).where(Wilayah.is_active.is_(True))) or 0)
    return data


@router.post("/internal/maintenance")
def maintenance(db: Session = Depends(get_db)) -> dict:
    released = locks.release_expired(db)
    reminders = 0
    now = datetime.now(timezone.utc)
    pending = db.scalars(
        select(Lhpp).where(Lhpp.is_uploaded.is_(False), Lhpp.wajib.is_(True), Lhpp.deadline_at.is_not(None))
    ).all()
    for lhpp in pending:
        sisa = (lhpp.deadline_at - now).days
        if sisa <= 2:
            penawaran = db.get(Penawaran, lhpp.penawaran_id)
            notify.notify(
                db,
                f"⏰ *Reminder LHPP*\nPenawaran {penawaran.nomor_surat if penawaran else '-'} "
                f"belum diunggah. Sisa {sisa} hari (deadline {lhpp.deadline_at:%d-%m-%Y}).",
                "ADMIN_GRUP",
                lhpp.wilayah_id,
                roles=(),
            )
            lhpp.reminder_count = (lhpp.reminder_count or 0) + 1
            reminders += 1
    db.commit()
    return {"lock_released": released, "lhpp_reminder": reminders}
