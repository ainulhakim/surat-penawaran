from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, is_pusat, require_roles
from app.db.session import get_db
from app.models import (
    BookingStatus,
    Client,
    Invoice,
    InvoiceStatus,
    Lhpp,
    Penawaran,
    PenawaranStatus,
    Pic,
    PicBooking,
    Sklk3,
    SuratTugas,
    SuratTugasStatus,
    User,
    UserRole,
    Wilayah,
)
from app.schemas.execution import (
    BookingCreate,
    BookingOut,
    BookingResponse,
    InvoiceFakturIn,
    InvoiceIn,
    LhppUpdate,
    PicCreate,
    PicOut,
    Sklk3In,
)
from app.services import notify
from app.services.audit import log_action
from app.services.files import save_base64_image
from app.services.numbering import next_surat_tugas_number
from app.services.pdf import render_surat_tugas

router = APIRouter(tags=["eksekusi"])

ADMIN_ROLES = (UserRole.ADMIN_WILAYAH, UserRole.SUPERADMIN)


def _scope_wilayah(user: User) -> int | None:
    return None if is_pusat(user) else user.wilayah_id


# ---------------- PIC ----------------
@router.get("/pic", response_model=list[PicOut])
def list_pic(
    wilayah_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Pic]:
    stmt = select(Pic).order_by(Pic.nama)
    scope = _scope_wilayah(user)
    if scope is not None:
        stmt = stmt.where(Pic.wilayah_id == scope)
    elif wilayah_id is not None:
        stmt = stmt.where(Pic.wilayah_id == wilayah_id)
    return list(db.scalars(stmt).all())


@router.post("/pic", response_model=PicOut, status_code=201)
def create_pic(
    payload: PicCreate,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> Pic:
    data = payload.model_dump()
    if not is_pusat(user):
        data["wilayah_id"] = user.wilayah_id
    pic = Pic(**data)
    db.add(pic)
    db.flush()
    log_action(db, user, "CREATE", "pic", pic.id, pic.nama)
    db.commit()
    db.refresh(pic)
    return pic


@router.get("/pic/agenda")
def agenda_pic(
    mulai: date | None = None,
    sampai: date | None = None,
    pic_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    mulai = mulai or date.today()
    sampai = sampai or (mulai + timedelta(days=30))
    stmt = (
        select(PicBooking, Pic.nama, Client.nama_perusahaan, Penawaran.nomor_surat)
        .join(Pic, Pic.id == PicBooking.pic_id)
        .join(Penawaran, Penawaran.id == PicBooking.penawaran_id)
        .join(Client, Client.id == Penawaran.client_id)
        .where(PicBooking.tanggal_tugas.between(mulai, sampai))
        .order_by(PicBooking.tanggal_tugas)
    )
    scope = _scope_wilayah(user)
    if scope is not None:
        stmt = stmt.where(PicBooking.wilayah_id == scope)
    if pic_id:
        stmt = stmt.where(PicBooking.pic_id == pic_id)
    return [
        {
            "booking_id": b.id,
            "pic": nama,
            "pic_id": b.pic_id,
            "tanggal": b.tanggal_tugas.isoformat(),
            "tanggal_usulan": b.tanggal_usulan.isoformat() if b.tanggal_usulan else None,
            "status": b.status,
            "penawaran": nomor,
            "client": perusahaan,
        }
        for b, nama, perusahaan, nomor in db.execute(stmt).all()
    ]


# ---------------- Booking PIC ----------------
@router.post("/booking", response_model=BookingOut, status_code=201)
def create_booking(
    payload: BookingCreate,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> PicBooking:
    penawaran = db.get(Penawaran, payload.penawaran_id)
    if not penawaran:
        raise HTTPException(status_code=404, detail="Penawaran tidak ditemukan")
    if not is_pusat(user) and penawaran.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan penawaran wilayah Anda")
    if PenawaranStatus(penawaran.status) not in {PenawaranStatus.DEAL, PenawaranStatus.BOOKING_PIC}:
        raise HTTPException(status_code=400, detail="Booking hanya untuk penawaran status DEAL")

    bentrok = db.scalar(
        select(PicBooking).where(
            PicBooking.pic_id == payload.pic_id,
            PicBooking.tanggal_tugas == payload.tanggal_tugas,
            PicBooking.status.in_([BookingStatus.DIAJUKAN, BookingStatus.DISETUJUI]),
        )
    )
    if bentrok:
        raise HTTPException(status_code=409, detail="PIC sudah punya agenda di tanggal tersebut")

    pic = db.get(Pic, payload.pic_id)
    if not pic or not pic.is_aktif:
        raise HTTPException(status_code=404, detail="PIC tidak ditemukan / tidak aktif")

    booking = PicBooking(
        penawaran_id=penawaran.id,
        pic_id=pic.id,
        wilayah_id=penawaran.wilayah_id,
        created_by=user.id,
        tanggal_tugas=payload.tanggal_tugas,
        catatan=payload.catatan,
        status=BookingStatus.DIAJUKAN,
    )
    penawaran.status = PenawaranStatus.BOOKING_PIC
    db.add(booking)
    db.flush()
    log_action(db, user, "CREATE", "pic_booking", booking.id)

    client = db.get(Client, penawaran.client_id)
    target = [pic.telegram_chat_id] if pic.telegram_chat_id else []
    if target:
        notify.send_telegram(
            f"📅 *Penjadwalan tugas*\nPIC: {pic.nama}\nClient: {client.nama_perusahaan} ({client.kota})\n"
            f"Tanggal: {payload.tanggal_tugas}\nNomor: {penawaran.nomor_surat}\n"
            f"Balas APPROVE atau RESCHEDULE melalui aplikasi.",
            target,
        )
    notify.notify(
        db,
        f"📅 Booking PIC diajukan: {pic.nama} untuk {client.nama_perusahaan} pada {payload.tanggal_tugas}.",
        "ADMIN_GRUP",
        penawaran.wilayah_id,
    )
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/booking/{booking_id}/respond", response_model=BookingOut)
def respond_booking(
    booking_id: int,
    payload: BookingResponse,
    user: User = Depends(require_roles(UserRole.PIC, UserRole.ADMIN_WILAYAH, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> PicBooking:
    booking = db.get(PicBooking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking tidak ditemukan")
    if not is_pusat(user) and UserRole(user.role) != UserRole.PIC and booking.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Tidak boleh mengubah booking wilayah lain")

    if payload.aksi == "APPROVE":
        booking.status = BookingStatus.DISETUJUI
    else:
        if not payload.tanggal_usulan:
            raise HTTPException(status_code=400, detail="Tanggal usulan wajib diisi untuk reschedule")
        booking.status = BookingStatus.RESCHEDULE
        booking.tanggal_usulan = payload.tanggal_usulan
        booking.alasan_reschedule = payload.alasan
    booking.responded_at = datetime.now(timezone.utc)
    log_action(db, user, payload.aksi, "pic_booking", booking.id)
    db.commit()
    db.refresh(booking)

    penawaran = db.get(Penawaran, booking.penawaran_id)
    notify.notify(
        db,
        f"📅 Booking PIC #{booking.id}: {payload.aksi}. "
        f"{'Tanggal disetujui ' + str(booking.tanggal_tugas) if payload.aksi == 'APPROVE' else 'Usulan reschedule ' + str(booking.tanggal_usulan)}",
        "ADMIN_GRUP",
        booking.wilayah_id,
        roles=(UserRole.ADMIN_WILAYAH,),
    )
    return booking


# ---------------- Surat Tugas ----------------
@router.post("/surat-tugas/dari-booking/{booking_id}")
def buat_surat_tugas(
    booking_id: int,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    booking = db.get(PicBooking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking tidak ditemukan")
    if not is_pusat(user) and booking.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan booking wilayah Anda")
    if db.scalar(select(SuratTugas).where(SuratTugas.booking_id == booking_id)):
        raise HTTPException(status_code=409, detail="Surat tugas untuk booking ini sudah ada")

    penawaran = db.get(Penawaran, booking.penawaran_id)
    wilayah = db.get(Wilayah, booking.wilayah_id)
    pic = db.get(Pic, booking.pic_id)
    client = db.get(Client, penawaran.client_id)

    st = SuratTugas(
        nomor=next_surat_tugas_number(db, wilayah),
        penawaran_id=penawaran.id,
        booking_id=booking.id,
        pic_id=pic.id,
        wilayah_id=wilayah.id,
        perihal=f"Penugasan survey/peninjauan {client.nama_perusahaan}",
        tujuan=f"Melaksanakan peninjauan lokasi {client.nama_perusahaan}, {client.alamat}, {client.kota} "
               f"terkait penawaran {penawaran.nomor_surat}.",
        tanggal_tugas=booking.tanggal_usulan or booking.tanggal_tugas,
        status=SuratTugasStatus.MENUNGGU_SPV,
    )
    db.add(st)
    db.flush()
    log_action(db, user, "CREATE", "surat_tugas", st.id, st.nomor)
    db.commit()

    notify.notify(
        db,
        f"✉️ *Surat Tugas menunggu tanda tangan*\nNo: {st.nomor}\nPIC: {pic.nama}\n"
        f"Tanggal: {st.tanggal_tugas}\nClient: {client.nama_perusahaan}\nSilakan Approve dengan tanda tangan digital.",
        "SPV_APPROVAL",
        wilayah.id,
        roles=(UserRole.SPV,),
    )
    return {"id": st.id, "nomor": st.nomor, "status": st.status}


@router.post("/surat-tugas/{st_id}/approve")
def approve_surat_tugas(
    st_id: int,
    payload: dict,
    user: User = Depends(require_roles(UserRole.SPV, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    st = db.get(SuratTugas, st_id)
    if not st:
        raise HTTPException(status_code=404, detail="Surat tugas tidak ditemukan")
    if not is_pusat(user) and st.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan surat tugas wilayah Anda")

    ttd_path = save_base64_image(payload.get("ttd_image_base64", ""), "ttd", f"spv{user.id}") or user.ttd_image_path
    if not ttd_path:
        raise HTTPException(status_code=400, detail="Tanda tangan digital wajib untuk approve")
    if not user.ttd_image_path:
        user.ttd_image_path = ttd_path

    st.status = SuratTugasStatus.DISETUJUI
    st.ttd_spv_path = ttd_path
    st.approved_by = user.id
    st.approved_at = datetime.now(timezone.utc)

    wilayah = db.get(Wilayah, st.wilayah_id)
    pic = db.get(Pic, st.pic_id)
    penawaran = db.get(Penawaran, st.penawaran_id)
    penawaran.status = PenawaranStatus.SURAT_TUGAS
    pdf_path = f"{settings.UPLOAD_DIR}/surat_tugas/{st.nomor.replace('/', '-')}.pdf"
    render_surat_tugas(
        nomor=st.nomor,
        wilayah_nama=wilayah.nama,
        wilayah_alamat=f"{wilayah.alamat} {wilayah.kota} {wilayah.kodepos}".strip(),
        pic_nama=pic.nama,
        pic_jabatan=pic.keahlian,
        perihal=st.perihal,
        tujuan=st.tujuan,
        tanggal_tugas=st.tanggal_tugas,
        penanggung_jawab=user.nama,
        kota_terbit=wilayah.kota or "Jakarta",
        ttd_path=ttd_path,
        output_path=pdf_path,
    )
    st.pdf_path = pdf_path
    log_action(db, user, "APPROVE", "surat_tugas", st.id, st.nomor)
    db.commit()

    notify.notify(
        db,
        f"✅ Surat Tugas {st.nomor} telah ditandatangani. PDF siap diunduh & dicetak.",
        "ADMIN_GRUP",
        st.wilayah_id,
        roles=(UserRole.ADMIN_WILAYAH,),
    )
    return {"detail": "Surat tugas disetujui", "pdf_path": pdf_path}


@router.get("/surat-tugas/{st_id}/pdf")
def unduh_surat_tugas(
    st_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    st = db.get(SuratTugas, st_id)
    if not st or not st.pdf_path:
        raise HTTPException(status_code=404, detail="PDF belum tersedia")
    if not is_pusat(user) and user.wilayah_id != st.wilayah_id and UserRole(user.role) != UserRole.PIC:
        raise HTTPException(status_code=403, detail="Tidak berhak mengunduh surat tugas ini")
    return FileResponse(st.pdf_path, media_type="application/pdf", filename=f"{st.nomor.replace('/', '-')}.pdf")


# ---------------- LHPP, SKLK3, Invoice ----------------
@router.post("/lhpp/{penawaran_id}")
def siapkan_lhpp(
    penawaran_id: int,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    penawaran = db.get(Penawaran, penawaran_id)
    if not penawaran:
        raise HTTPException(status_code=404, detail="Penawaran tidak ditemukan")
    if not is_pusat(user) and penawaran.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan penawaran wilayah Anda")

    existing = db.scalar(select(Lhpp).where(Lhpp.penawaran_id == penawaran_id))
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=settings.LHPP_DEADLINE_DAYS)
    if existing:
        existing.deadline_at = deadline
        existing.wajib = True
        lhpp = existing
    else:
        lhpp = Lhpp(
            penawaran_id=penawaran_id,
            wilayah_id=penawaran.wilayah_id,
            wajib=True,
            deadline_at=deadline,
            checklist='{"lhpp_external": false, "sklk3": false}',
        )
        db.add(lhpp)
    penawaran.status = PenawaranStatus.PELAKSANAAN
    db.flush()
    log_action(db, user, "SETUP_LHPP", "lhpp", lhpp.id, f"deadline={deadline.date()}")
    db.commit()

    notify.notify(
        db,
        f"🚧 LHPP wajib diunggah ke aplikasi eksternal maksimal {settings.LHPP_DEADLINE_DAYS} hari "
        f"(deadline {deadline:%d-%m-%Y}). Penawaran {penawaran.nomor_surat}.",
        "ADMIN_GRUP",
        penawaran.wilayah_id,
        roles=(UserRole.ADMIN_WILAYAH,),
    )
    return {"lhpp_id": lhpp.id, "deadline_at": deadline.isoformat()}


@router.patch("/lhpp/{lhpp_id}")
def update_lhpp(
    lhpp_id: int,
    payload: LhppUpdate,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    lhpp = db.get(Lhpp, lhpp_id)
    if not lhpp:
        raise HTTPException(status_code=404, detail="Data LHPP tidak ditemukan")
    if not is_pusat(user) and lhpp.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan LHPP wilayah Anda")

    import json

    data = payload.model_dump(exclude_unset=True)
    if data.get("tanggal_selesai"):
        lhpp.tanggal_selesai = data["tanggal_selesai"]
        penawaran = db.get(Penawaran, lhpp.penawaran_id)
        penawaran.status = PenawaranStatus.LHPP
    if data.get("catatan") is not None:
        lhpp.catatan = data["catatan"]
    if data.get("checklist") is not None:
        lhpp.checklist = json.dumps(data["checklist"])
    if data.get("bukti_screenshot_base64"):
        path = save_base64_image(data["bukti_screenshot_base64"], "lhpp", f"lhpp{lhpp.id}")
        if path:
            lhpp.bukti_screenshot_path = path
    if data.get("is_uploaded") is not None:
        lhpp.is_uploaded = bool(data["is_uploaded"])
        lhpp.uploaded_at = datetime.now(timezone.utc) if lhpp.is_uploaded else None
    log_action(db, user, "UPDATE", "lhpp", lhpp.id)
    db.commit()
    return {
        "lhpp_id": lhpp.id,
        "is_uploaded": lhpp.is_uploaded,
        "deadline_at": lhpp.deadline_at.isoformat() if lhpp.deadline_at else None,
    }


@router.post("/sklk3/{penawaran_id}")
def submit_sklk3(
    penawaran_id: int,
    payload: Sklk3In,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    penawaran = db.get(Penawaran, penawaran_id)
    if not penawaran:
        raise HTTPException(status_code=404, detail="Penawaran tidak ditemukan")
    if not is_pusat(user) and penawaran.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan penawaran wilayah Anda")

    sklk3 = db.scalar(select(Sklk3).where(Sklk3.penawaran_id == penawaran_id))
    if not sklk3:
        sklk3 = Sklk3(penawaran_id=penawaran_id, wilayah_id=penawaran.wilayah_id)
        db.add(sklk3)
    sklk3.nomor = payload.nomor
    sklk3.tanggal_muncul = payload.tanggal_muncul
    sklk3.catatan = payload.catatan
    sklk3.submitted_by = user.id
    sklk3.submitted_at = datetime.now(timezone.utc)
    penawaran.status = PenawaranStatus.SKLK3
    db.flush()
    log_action(db, user, "SUBMIT", "sklk3", sklk3.id)
    db.commit()
    return {"sklk3_id": sklk3.id, "status": "tersimpan"}


@router.post("/invoice/{penawaran_id}")
def terbitkan_invoice(
    penawaran_id: int,
    payload: InvoiceIn,
    user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    penawaran = db.get(Penawaran, penawaran_id)
    if not penawaran:
        raise HTTPException(status_code=404, detail="Penawaran tidak ditemukan")
    if not is_pusat(user) and penawaran.wilayah_id != user.wilayah_id:
        raise HTTPException(status_code=403, detail="Bukan penawaran wilayah Anda")

    invoice = Invoice(
        penawaran_id=penawaran.id,
        wilayah_id=penawaran.wilayah_id,
        nomor=f"INV/{penawaran.nomor_surat}",
        tanggal=payload.tanggal or date.today(),
        tanggal_manual=payload.tanggal is not None,
        nominal=payload.nominal if payload.nominal is not None else penawaran.harga_total,
        keterangan=payload.keterangan,
        status=InvoiceStatus.TERBIT,
        notif_sent_at=datetime.now(timezone.utc),
    )
    penawaran.status = PenawaranStatus.INVOICE
    db.add(invoice)
    db.flush()
    log_action(db, user, "INVOICE", "invoice", invoice.id, invoice.nomor)
    db.commit()

    client = db.get(Client, penawaran.client_id)
    sent = notify.notify(
        db,
        f"🧾 *Invoice terbit*\nNo: {invoice.nomor}\nClient: {client.nama_perusahaan} ({client.kota})\n"
        f"Tanggal: {invoice.tanggal}\nNilai: Rp{invoice.nominal:,.0f}\nSilakan buat faktur.",
        "KEUANGAN",
        penawaran.wilayah_id,
        roles=(UserRole.KEUANGAN,),
    )
    return {"invoice_id": invoice.id, "nomor": invoice.nomor, "notif_terkirim": sent}


@router.post("/invoice/{invoice_id}/faktur")
def set_faktur(
    invoice_id: int,
    payload: InvoiceFakturIn,
    user: User = Depends(require_roles(UserRole.KEUANGAN, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan")
    invoice.faktur_nomor = payload.faktur_nomor
    invoice.faktur_at = datetime.now(timezone.utc)
    invoice.status = InvoiceStatus.FAKTUR_DIBUAT
    penawaran = db.get(Penawaran, invoice.penawaran_id)
    penawaran.status = PenawaranStatus.SELESAI
    log_action(db, user, "FAKTUR", "invoice", invoice.id, payload.faktur_nomor)
    db.commit()
    return {"detail": "Faktur dicatat", "invoice_id": invoice.id}
