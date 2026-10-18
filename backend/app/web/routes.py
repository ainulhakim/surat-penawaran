"""Halaman HTML (Jinja2 + Bootstrap) untuk Web Apps Surat Penawaran.

Lapisan ini sengaja TIPIS: seluruh aturan bisnis tetap dijalankan oleh fungsi
endpoint di ``app/api/v1/*`` yang dipanggil langsung (in-process), jadi tidak ada
duplikasi logika antara API dan UI.
"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.v1 import dashboard as dashboard_api
from app.api.v1 import execution as exec_api
from app.api.v1 import master as master_api
from app.api.v1 import penawaran as pen_api
from app.api.v1 import users as users_api
from app.api.v1 import wilayah as wilayah_api
from app.api.v1.auth import change_password as api_change_password
from app.api.v1.auth import login as api_login
from app.api.v1.penawaran import approval_penawaran as api_approval
from app.api.v1.penawaran import create_penawaran as api_create_penawaran
from app.api.v1.penawaran import deal_penawaran as api_deal
from app.api.v1.penawaran import submit_penawaran as api_submit
from app.api.v1.penawaran import update_penawaran as api_update_penawaran
from app.core.config import settings
from app.core.security import verify_password
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalLog,
    Bidang,
    BookingStatus,
    Client,
    Invoice,
    InvoiceStatus,
    Kategori,
    Lhpp,
    Objek,
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
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.execution import (
    BookingCreate,
    BookingResponse,
    InvoiceFakturIn,
    InvoiceIn,
    LhppUpdate,
    PicCreate,
    Sklk3In,
)
from app.schemas.master import BidangCreate, KategoriCreate, ObjekCreate
from app.schemas.penawaran import ApprovalIn, DealIn, ItemIn, PenawaranCreate, PenawaranUpdate
from app.schemas.user import UserCreate, UserUpdate
from app.schemas.wilayah import WilayahCreate, WilayahUpdate
from app.web.deps import (
    ADMIN_ROLES,
    Forbidden,
    NotAuthenticated,
    is_pusat,
    web_roles,
    web_user,
    web_user_optional,
)
from app.web.session import clear_session, set_session

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

web_router = APIRouter(include_in_schema=False)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def rupiah(value) -> str:
    if value is None:
        return "-"
    try:
        return "Rp " + f"{Decimal(value):,.0f}".replace(",", ".")
    except (InvalidOperation, ValueError):
        return str(value)


def tanggal(value) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value
    return value.strftime("%d-%m-%Y")


def tanggal_waktu(value) -> str:
    if not value:
        return "-"
    return value.strftime("%d-%m-%Y %H:%M")


def status_badge(status: str) -> str:
    mapping = {
        "DRAFT": "secondary",
        "MENUNGGU_SPV": "warning text-dark",
        "REVISI": "danger",
        "APPROVED": "info text-dark",
        "DEAL": "primary",
        "BOOKING_PIC": "primary",
        "SURAT_TUGAS": "primary",
        "PELAKSANAAN": "primary",
        "LHPP": "primary",
        "SKLK3": "primary",
        "INVOICE": "success",
        "SELESAI": "success",
        "BATAL": "dark",
        "DIAJUKAN": "warning text-dark",
        "DISETUJUI": "success",
        "RESCHEDULE": "danger",
        "DIBATALKAN": "dark",
        "TERBIT": "warning text-dark",
        "FAKTUR_DIBUAT": "success",
        "MENUNGGU": "secondary",
        "FREE": "success",
        "LOCKED": "danger",
    }
    return mapping.get(str(status), "secondary")


templates.env.filters["rupiah"] = rupiah
templates.env.filters["tanggal"] = tanggal
templates.env.filters["tanggal_waktu"] = tanggal_waktu
templates.env.filters["badge"] = status_badge


def money(value: str | None) -> Decimal:
    raw = "".join(ch for ch in str(value or "0") if ch.isdigit() or ch in "-.")
    try:
        return Decimal(raw or "0")
    except InvalidOperation:
        return Decimal("0")


def to_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _sep(url: str) -> str:
    return "&" if "?" in url else "?"


def back(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    if err:
        url = f"{url}{_sep(url)}err={quote(str(err)[:300])}"
    elif msg:
        url = f"{url}{_sep(url)}msg={quote(str(msg)[:300])}"
    return RedirectResponse(url, status_code=303)


def run(call, url: str, msg: str = "Berhasil"):
    """Jalankan aksi API; ubah HTTPException jadi pesan error di halaman."""
    try:
        result = call()
        return back(url, msg=msg), result
    except HTTPException as exc:
        return back(url, err=str(exc.detail)), None
    except Exception as exc:  # noqa: BLE001
        return back(url, err=f"{type(exc).__name__}: {exc}"), None


def render(
    request: Request,
    name: str,
    user: User | None = None,
    status_code: int = 200,
    **ctx,
):
    base = {
        "request": request,
        "user": user,
        "app_name": settings.APP_NAME,
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
        "is_pusat": bool(user and is_pusat(user)),
        "nav": "dashboard",
        "today": date.today(),
    }
    base.update(ctx)
    return templates.TemplateResponse(request, name, base, status_code=status_code)


def render_error(request: Request, kode: int, pesan: str, user: User | None = None):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "user": user,
            "app_name": settings.APP_NAME,
            "kode": kode,
            "pesan": pesan,
            "msg": None,
            "err": None,
            "nav": "",
            "is_pusat": False,
            "today": date.today(),
        },
        status_code=kode,
    )


def _nama_wilayah(db: Session) -> dict[int, str]:
    return {w.id: w.nama for w in db.scalars(select(Wilayah)).all()}


def _nama_user(db: Session) -> dict[int, str]:
    return {u.id: u.nama for u in db.scalars(select(User)).all()}


def _status_menu() -> list[tuple[str, str]]:
    return [(s.value, s.value.replace("_", " ").title()) for s in PenawaranStatus]


# --------------------------------------------------------------------------- #
# Auth & profil
# --------------------------------------------------------------------------- #


@web_router.get("/login")
def halaman_login(request: Request, user: User | None = Depends(web_user_optional)):
    if user:
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", user=None, next=request.query_params.get("next", "/"))


@web_router.post("/login")
def proses_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    try:
        token = api_login(LoginRequest(email=email, password=password), db=db)
    except HTTPException as exc:
        return back("/login", err=str(exc.detail))
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    response = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    set_session(response, user)
    return response


@web_router.get("/logout")
def proses_logout():
    response = RedirectResponse("/login?msg=Anda+telah+keluar", status_code=303)
    clear_session(response)
    return response


@web_router.get("/profil")
def halaman_profil(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    wilayah = db.get(Wilayah, user.wilayah_id) if user.wilayah_id else None
    return render(request, "profil.html", user=user, nav="profil", wilayah=wilayah)


@web_router.post("/profil/password")
def ganti_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    konfirmasi: str = Form(...),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    if new_password != konfirmasi:
        return back("/profil", err="Konfirmasi password tidak sama")
    try:
        api_change_password(
            ChangePasswordRequest(old_password=old_password, new_password=new_password),
            user=user,
            db=db,
        )
    except HTTPException as exc:
        return back("/profil", err=str(exc.detail))
    return back("/profil", msg="Password berhasil diubah")


@web_router.post("/profil/ttd")
def unggah_ttd(
    request: Request,
    image_base64: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    if not image_base64.strip():
        return back("/profil", err="Gambar tanda tangan kosong")
    resp, _ = run(
        lambda: users_api.upload_ttd({"image_base64": image_base64}, user=user, db=db),
        "/profil",
        msg="Tanda tangan tersimpan",
    )
    return resp


@web_router.get("/profil/ttd.png")
def lihat_ttd(
    user: User = Depends(web_user),
):
    """Kirim gambar tanda tangan milik user (dipakai tombol 'pakai ttd tersimpan')."""
    if not user.ttd_image_path:
        return RedirectResponse("/static/style.css", status_code=307)
    return FileResponse(user.ttd_image_path, media_type="image/png")


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #


@web_router.get("/")
def beranda(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    data = dashboard_api.summary(user=user, db=db)
    terbaru = db.scalars(
        select(Penawaran)
        .options(selectinload(Penawaran.items))
        .order_by(Penawaran.created_at.desc())
        .limit(8)
    ).all()
    if not is_pusat(user):
        terbaru = [p for p in terbaru if p.wilayah_id == user.wilayah_id]
    klien_map = {c.id: c for c in db.scalars(select(Client)).all()}
    return render(
        request,
        "dashboard.html",
        user=user,
        nav="dashboard",
        data=data,
        terbaru=terbaru,
        klien_map=klien_map,
        wilayah_map=_nama_wilayah(db),
    )


# --------------------------------------------------------------------------- #
# Klien
# --------------------------------------------------------------------------- #


@web_router.get("/klien")
def daftar_klien(
    request: Request,
    q: str = "",
    user: User = Depends(web_roles(*ADMIN_ROLES, UserRole.SPV, UserRole.KEUANGAN)),
    db: Session = Depends(get_db),
):
    stmt = select(Client).where(Client.is_active.is_(True)).order_by(Client.nama_perusahaan)
    if not is_pusat(user):
        stmt = stmt.where(Client.wilayah_id == user.wilayah_id)
    if q.strip():
        like = f"%{q.lower().strip()}%"
        stmt = stmt.where(
            or_(
                func.lower(Client.nama_perusahaan).like(like),
                func.lower(Client.email).like(like),
                func.lower(Client.kota).like(like),
                func.lower(Client.pic).like(like),
            )
        )
    rows = db.scalars(stmt.limit(300)).all()
    from app.services.locks import active_lock

    lock_map = {c.id: active_lock(db, c.id) for c in rows}
    return render(
        request,
        "klien_list.html",
        user=user,
        nav="klien",
        rows=rows,
        lock_map=lock_map,
        wilayah_map=_nama_wilayah(db),
        q=q,
    )


@web_router.get("/klien/baru")
def form_klien_baru(request: Request, user: User = Depends(web_roles(*ADMIN_ROLES))):
    return render(request, "klien_form.html", user=user, nav="klien", row=None)


@web_router.post("/klien/baru")
def simpan_klien_baru(
    request: Request,
    nama_perusahaan: str = Form(...),
    email: str = Form(""),
    no_telpon: str = Form(""),
    pic: str = Form(""),
    no_pic: str = Form(""),
    alamat: str = Form(""),
    kota: str = Form(""),
    provinsi: str = Form(""),
    kodepos: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = ClientCreate(
        nama_perusahaan=nama_perusahaan.strip(),
        email=email.strip(),
        no_telpon=no_telpon.strip(),
        pic=pic.strip(),
        no_pic=no_pic.strip(),
        alamat=alamat.strip(),
        kota=kota.strip(),
        provinsi=provinsi.strip(),
        kodepos=kodepos.strip(),
    )
    try:
        from app.api.v1.clients import create_client

        created = create_client(payload, user=user, db=db)
    except HTTPException as exc:
        return back("/klien/baru", err=str(exc.detail))
    return back(f"/klien/{created.id}/edit", msg="Klien baru tersimpan")


@web_router.get("/klien/{client_id}/edit")
def form_klien_edit(
    request: Request,
    client_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES, UserRole.SPV)),
    db: Session = Depends(get_db),
):
    row = db.get(Client, client_id)
    if not row:
        return back("/klien", err="Klien tidak ditemukan")
    from app.services.locks import active_lock

    return render(
        request,
        "klien_form.html",
        user=user,
        nav="klien",
        row=row,
        lock=active_lock(db, client_id),
        wilayah_map=_nama_wilayah(db),
    )


@web_router.post("/klien/{client_id}/edit")
def simpan_klien_edit(
    request: Request,
    client_id: int,
    nama_perusahaan: str = Form(...),
    email: str = Form(""),
    no_telpon: str = Form(""),
    pic: str = Form(""),
    no_pic: str = Form(""),
    alamat: str = Form(""),
    kota: str = Form(""),
    provinsi: str = Form(""),
    kodepos: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES, UserRole.SPV)),
    db: Session = Depends(get_db),
):
    from app.api.v1.clients import update_client

    payload = ClientUpdate(
        nama_perusahaan=nama_perusahaan.strip(),
        email=email.strip(),
        no_telpon=no_telpon.strip(),
        pic=pic.strip(),
        no_pic=no_pic.strip(),
        alamat=alamat.strip(),
        kota=kota.strip(),
        provinsi=provinsi.strip(),
        kodepos=kodepos.strip(),
    )
    resp, _ = run(
        lambda: update_client(client_id, payload, user=user, db=db),
        f"/klien/{client_id}/edit",
        msg="Perubahan klien tersimpan",
    )
    return resp


@web_router.post("/klien/{client_id}/hapus")
def hapus_klien(
    client_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    from app.api.v1.clients import delete_client

    resp, _ = run(lambda: delete_client(client_id, user=user, db=db), "/klien", msg="Klien dinonaktifkan")
    return resp


# --------------------------------------------------------------------------- #
# Penawaran
# --------------------------------------------------------------------------- #


@web_router.get("/penawaran")
def daftar_penawaran(
    request: Request,
    status: str = "",
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Penawaran, Client)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(Penawaran.created_at.desc())
        .limit(300)
    )
    if not is_pusat(user):
        stmt = stmt.where(Penawaran.wilayah_id == user.wilayah_id)
    if status:
        stmt = stmt.where(Penawaran.status == status)
    rows = db.execute(stmt).all()
    return render(
        request,
        "penawaran_list.html",
        user=user,
        nav="penawaran",
        rows=rows,
        status=status,
        status_menu=_status_menu(),
        wilayah_map=_nama_wilayah(db),
    )


@web_router.get("/penawaran/baru")
def form_penawaran_baru(
    request: Request,
    client_id: int | None = None,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    stmt = select(Client).where(Client.is_active.is_(True)).order_by(Client.nama_perusahaan)
    if not is_pusat(user):
        stmt = stmt.where(Client.wilayah_id == user.wilayah_id)
    klien = db.scalars(stmt.limit(500)).all()
    kategori = db.scalars(select(Kategori).order_by(Kategori.nama)).all()
    bidang = db.scalars(select(Bidang).order_by(Bidang.nama)).all()
    objek = db.scalars(select(Objek).order_by(Objek.nama)).all()
    from app.services.locks import active_lock

    return render(
        request,
        "penawaran_form.html",
        user=user,
        nav="penawaran",
        penawaran=None,
        klien=klien,
        kategori=kategori,
        bidang=bidang,
        objek=objek,
        client_id=client_id,
        lock_map={c.id: active_lock(db, c.id) for c in klien},
    )


def _items_from_form(
    uraian: list[str],
    spesifikasi: list[str],
    qty: list[str],
    satuan: list[str],
    harga: list[str],
    nego: list[str],
    harga_nego: list[str],
    kategori_id: list[str],
    bidang_id: list[str],
    objek_id: list[str],
) -> list[ItemIn]:
    items: list[ItemIn] = []
    for idx, u in enumerate(uraian):
        if not (u or "").strip():
            continue
        items.append(
            ItemIn(
                uraian=u.strip(),
                spesifikasi=(spesifikasi[idx] if idx < len(spesifikasi) else "") or "",
                qty=money(qty[idx] if idx < len(qty) else "1"),
                satuan=(satuan[idx] if idx < len(satuan) else "unit") or "unit",
                harga_satuan=money(harga[idx] if idx < len(harga) else "0"),
                is_nego=(nego[idx] if idx < len(nego) else "") in {"on", "true", "1"},
                harga_nego=money(harga_nego[idx]) if idx < len(harga_nego) and harga_nego[idx] else None,
                kategori_id=to_int(kategori_id[idx], None) if idx < len(kategori_id) else None,
                bidang_id=to_int(bidang_id[idx], None) if idx < len(bidang_id) else None,
                objek_id=to_int(objek_id[idx], None) if idx < len(objek_id) else None,
            )
        )
    return items


@web_router.post("/penawaran/baru")
def simpan_penawaran_baru(
    client_id: int = Form(...),
    perihal: str = Form(""),
    catatan: str = Form(""),
    is_nego: str = Form(""),
    uraian: list[str] = Form([]),
    spesifikasi: list[str] = Form([]),
    qty: list[str] = Form([]),
    satuan: list[str] = Form([]),
    harga: list[str] = Form([]),
    nego: list[str] = Form([]),
    harga_nego: list[str] = Form([]),
    kategori_id: list[str] = Form([]),
    bidang_id: list[str] = Form([]),
    objek_id: list[str] = Form([]),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = PenawaranCreate(
        client_id=client_id,
        perihal=perihal.strip(),
        catatan=catatan.strip(),
        is_nego=is_nego in {"on", "true", "1"},
        items=_items_from_form(
            uraian, spesifikasi, qty, satuan, harga, nego, harga_nego, kategori_id, bidang_id, objek_id
        ),
    )
    resp, result = run(
        lambda: api_create_penawaran(payload, user=user, db=db),
        "/penawaran/baru",
        msg="Penawaran dibuat",
    )
    if result is None:
        return resp
    return back(f"/penawaran/{result.id}", msg=f"Penawaran {result.nomor_surat} dibuat")


@web_router.get("/penawaran/{penawaran_id}")
def detail_penawaran(
    request: Request,
    penawaran_id: int,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    p = db.scalar(
        select(Penawaran).options(selectinload(Penawaran.items)).where(Penawaran.id == penawaran_id)
    )
    if not p:
        return back("/penawaran", err="Penawaran tidak ditemukan")
    if not is_pusat(user) and p.wilayah_id != user.wilayah_id:
        return back("/penawaran", err="Penawaran bersifat rahasia — bukan wilayah Anda")

    klien = db.get(Client, p.client_id)
    riwayat = db.scalars(
        select(ApprovalLog).where(ApprovalLog.penawaran_id == p.id).order_by(ApprovalLog.created_at)
    ).all()
    booking = db.scalar(select(PicBooking).where(PicBooking.penawaran_id == p.id).order_by(PicBooking.id.desc()))
    pic = db.get(Pic, booking.pic_id) if booking else None
    surat = db.scalar(select(SuratTugas).where(SuratTugas.penawaran_id == p.id))
    lhpp = db.scalar(select(Lhpp).where(Lhpp.penawaran_id == p.id))
    sklk3 = db.scalar(select(Sklk3).where(Sklk3.penawaran_id == p.id))
    invoice = db.scalar(select(Invoice).where(Invoice.penawaran_id == p.id).order_by(Invoice.id.desc()))
    from app.services.locks import active_lock

    return render(
        request,
        "penawaran_detail.html",
        user=user,
        nav="penawaran",
        p=p,
        klien=klien,
        riwayat=riwayat,
        user_map=_nama_user(db),
        wilayah=db.get(Wilayah, p.wilayah_id),
        lock=active_lock(db, p.client_id),
        booking=booking,
        pic=pic,
        surat=surat,
        lhpp=lhpp,
        sklk3=sklk3,
        invoice=invoice,
        pics=db.scalars(select(Pic).where(Pic.is_aktif.is_(True), Pic.wilayah_id == p.wilayah_id)).all(),
    )


@web_router.get("/penawaran/{penawaran_id}/edit")
def form_penawaran_edit(
    request: Request,
    penawaran_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    p = db.scalar(
        select(Penawaran).options(selectinload(Penawaran.items)).where(Penawaran.id == penawaran_id)
    )
    if not p:
        return back("/penawaran", err="Penawaran tidak ditemukan")
    if PenawaranStatus(p.status) not in {PenawaranStatus.DRAFT, PenawaranStatus.REVISI}:
        return back(f"/penawaran/{p.id}", err="Penawaran tidak dapat diubah pada status ini")
    klien = db.scalars(select(Client).order_by(Client.nama_perusahaan).limit(500)).all()
    return render(
        request,
        "penawaran_form.html",
        user=user,
        nav="penawaran",
        penawaran=p,
        klien=klien,
        kategori=db.scalars(select(Kategori).order_by(Kategori.nama)).all(),
        bidang=db.scalars(select(Bidang).order_by(Bidang.nama)).all(),
        objek=db.scalars(select(Objek).order_by(Objek.nama)).all(),
        client_id=p.client_id,
        lock_map={},
    )


@web_router.post("/penawaran/{penawaran_id}/edit")
def simpan_penawaran_edit(
    penawaran_id: int,
    perihal: str = Form(""),
    catatan: str = Form(""),
    is_nego: str = Form(""),
    uraian: list[str] = Form([]),
    spesifikasi: list[str] = Form([]),
    qty: list[str] = Form([]),
    satuan: list[str] = Form([]),
    harga: list[str] = Form([]),
    nego: list[str] = Form([]),
    harga_nego: list[str] = Form([]),
    kategori_id: list[str] = Form([]),
    bidang_id: list[str] = Form([]),
    objek_id: list[str] = Form([]),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = PenawaranUpdate(
        perihal=perihal.strip(),
        catatan=catatan.strip(),
        is_nego=is_nego in {"on", "true", "1"},
        items=[
            i.model_dump()
            for i in _items_from_form(
                uraian, spesifikasi, qty, satuan, harga, nego, harga_nego, kategori_id, bidang_id, objek_id
            )
        ],
    )
    resp, _ = run(
        lambda: api_update_penawaran(penawaran_id, payload, user=user, db=db),
        f"/penawaran/{penawaran_id}/edit",
        msg="Penawaran diperbarui",
    )
    return resp


@web_router.post("/penawaran/{penawaran_id}/submit")
def submit_penawaran_ui(
    penawaran_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: api_submit(penawaran_id, user=user, db=db),
        f"/penawaran/{penawaran_id}",
        msg="Penawaran diajukan ke SPV",
    )
    return resp


@web_router.post("/penawaran/{penawaran_id}/approval")
def approval_ui(
    penawaran_id: int,
    aksi: str = Form(...),
    catatan: str = Form(""),
    ttd_image_base64: str = Form(""),
    user: User = Depends(web_roles(UserRole.SPV, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    payload = ApprovalIn(aksi=aksi, catatan=catatan, ttd_image_base64=ttd_image_base64 or None)
    resp, _ = run(
        lambda: api_approval(penawaran_id, payload, user=user, db=db),
        f"/penawaran/{penawaran_id}",
        msg=f"Penawaran di-{aksi.lower()}",
    )
    return resp


@web_router.post("/penawaran/{penawaran_id}/deal")
def deal_ui(
    penawaran_id: int,
    tgl_po: str = Form(...),
    no_spk: str = Form(...),
    nilai_po: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        payload = DealIn(
            tgl_po=date.fromisoformat(tgl_po),
            no_spk=no_spk.strip(),
            nilai_po=money(nilai_po) if nilai_po.strip() else None,
        )
    except ValueError:
        return back(f"/penawaran/{penawaran_id}", err="Tanggal PO tidak valid")
    resp, _ = run(
        lambda: api_deal(penawaran_id, payload, user=user, db=db),
        f"/penawaran/{penawaran_id}",
        msg="Deal tercatat",
    )
    return resp


@web_router.get("/persetujuan")
def kotak_persetujuan(
    request: Request,
    user: User = Depends(web_roles(UserRole.SPV, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Penawaran, Client)
        .join(Client, Client.id == Penawaran.client_id)
        .where(Penawaran.status == PenawaranStatus.MENUNGGU_SPV)
        .order_by(Penawaran.created_at)
    )
    if not is_pusat(user):
        stmt = stmt.where(Penawaran.wilayah_id == user.wilayah_id)
    rows = db.execute(stmt).all()

    stmt_st = select(SuratTugas, Pic, Client).join(Pic, Pic.id == SuratTugas.pic_id).join(
        Penawaran, Penawaran.id == SuratTugas.penawaran_id
    ).join(Client, Client.id == Penawaran.client_id).where(
        SuratTugas.status == SuratTugasStatus.MENUNGGU_SPV
    )
    if not is_pusat(user):
        stmt_st = stmt_st.where(SuratTugas.wilayah_id == user.wilayah_id)
    surat_rows = db.execute(stmt_st).all()
    return render(
        request,
        "persetujuan.html",
        user=user,
        nav="persetujuan",
        rows=rows,
        surat_rows=surat_rows,
        wilayah_map=_nama_wilayah(db),
    )


# --------------------------------------------------------------------------- #
# PIC & Booking
# --------------------------------------------------------------------------- #


@web_router.get("/pic")
def daftar_pic(
    request: Request,
    user: User = Depends(web_roles(*ADMIN_ROLES, UserRole.SPV, UserRole.PIC)),
    db: Session = Depends(get_db),
):
    stmt = select(Pic).order_by(Pic.nama)
    if not is_pusat(user):
        stmt = stmt.where(Pic.wilayah_id == user.wilayah_id)
    from app.services import locks  # noqa: F401  (menjaga import konsisten)

    return render(
        request,
        "pic_list.html",
        user=user,
        nav="pic",
        rows=db.scalars(stmt).all(),
        wilayah_map=_nama_wilayah(db),
    )


@web_router.post("/pic/baru")
def simpan_pic(
    nama: str = Form(...),
    no_hp: str = Form(""),
    email: str = Form(""),
    keahlian: str = Form(""),
    telegram_chat_id: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = PicCreate(
        nama=nama.strip(),
        no_hp=no_hp.strip(),
        email=email.strip(),
        keahlian=keahlian.strip(),
        telegram_chat_id=telegram_chat_id.strip() or None,
    )
    resp, _ = run(lambda: exec_api.create_pic(payload, user=user, db=db), "/pic", msg="PIC tersimpan")
    return resp


@web_router.get("/agenda")
def agenda(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    rows = exec_api.agenda_pic(user=user, db=db)
    penawaran_deal = db.scalars(
        select(Penawaran).where(
            Penawaran.status.in_([PenawaranStatus.DEAL, PenawaranStatus.BOOKING_PIC])
        )
    ).all()
    if not is_pusat(user):
        penawaran_deal = [p for p in penawaran_deal if p.wilayah_id == user.wilayah_id]
    stmt_pic = select(Pic).where(Pic.is_aktif.is_(True)).order_by(Pic.nama)
    if not is_pusat(user):
        stmt_pic = stmt_pic.where(Pic.wilayah_id == user.wilayah_id)
    bookings = db.execute(
        select(PicBooking, Pic, Penawaran, Client)
        .join(Pic, Pic.id == PicBooking.pic_id)
        .join(Penawaran, Penawaran.id == PicBooking.penawaran_id)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(PicBooking.tanggal_tugas.desc())
        .limit(100)
    ).all()
    if not is_pusat(user):
        bookings = [b for b in bookings if b[0].wilayah_id == user.wilayah_id]
    klien_map = {c.id: c for c in db.scalars(select(Client)).all()}
    return render(
        request,
        "agenda.html",
        user=user,
        nav="agenda",
        rows=rows,
        penawaran_deal=penawaran_deal,
        klien_map=klien_map,
        pics=db.scalars(stmt_pic).all(),
        bookings=bookings,
    )


@web_router.post("/booking/baru")
def simpan_booking(
    penawaran_id: int = Form(...),
    pic_id: int = Form(...),
    tanggal_tugas: str = Form(...),
    catatan: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        payload = BookingCreate(
            penawaran_id=penawaran_id,
            pic_id=pic_id,
            tanggal_tugas=date.fromisoformat(tanggal_tugas),
            catatan=catatan.strip(),
        )
    except ValueError:
        return back("/agenda", err="Tanggal tugas tidak valid")
    resp, _ = run(lambda: exec_api.create_booking(payload, user=user, db=db), "/agenda", msg="Booking diajukan")
    return resp


@web_router.post("/booking/{booking_id}/respond")
def respond_booking_ui(
    booking_id: int,
    aksi: str = Form(...),
    tanggal_usulan: str = Form(""),
    alasan: str = Form(""),
    user: User = Depends(web_roles(UserRole.PIC, *ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = BookingResponse(
        aksi=aksi,
        tanggal_usulan=date.fromisoformat(tanggal_usulan) if tanggal_usulan.strip() else None,
        alasan=alasan.strip(),
    )
    resp, _ = run(
        lambda: exec_api.respond_booking(booking_id, payload, user=user, db=db),
        "/agenda",
        msg=f"Booking di-{aksi.lower()}",
    )
    return resp


# --------------------------------------------------------------------------- #
# Surat Tugas
# --------------------------------------------------------------------------- #


@web_router.get("/surat-tugas")
def daftar_surat_tugas(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(SuratTugas, Pic, Penawaran, Client)
        .join(Pic, Pic.id == SuratTugas.pic_id)
        .join(Penawaran, Penawaran.id == SuratTugas.penawaran_id)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(SuratTugas.created_at.desc())
        .limit(200)
    )
    if not is_pusat(user) and UserRole(user.role) != UserRole.PIC:
        stmt = stmt.where(SuratTugas.wilayah_id == user.wilayah_id)
    rows = db.execute(stmt).all()
    return render(request, "surat_tugas_list.html", user=user, nav="surat_tugas", rows=rows)


@web_router.post("/surat-tugas/dari-booking/{booking_id}")
def buat_surat_tugas_ui(
    booking_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: exec_api.buat_surat_tugas(booking_id, user=user, db=db),
        "/surat-tugas",
        msg="Surat tugas dibuat, menunggu tanda tangan SPV",
    )
    return resp


@web_router.post("/surat-tugas/{st_id}/approve")
def approve_surat_tugas_ui(
    st_id: int,
    ttd_image_base64: str = Form(""),
    user: User = Depends(web_roles(UserRole.SPV, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: exec_api.approve_surat_tugas(st_id, {"ttd_image_base64": ttd_image_base64}, user=user, db=db),
        "/surat-tugas",
        msg="Surat tugas ditandatangani, PDF siap",
    )
    return resp


@web_router.get("/surat-tugas/{st_id}/pdf")
def unduh_surat_tugas_ui(
    st_id: int,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    return exec_api.unduh_surat_tugas(st_id, user=user, db=db)


# --------------------------------------------------------------------------- #
# LHPP, SKLK3, Invoice
# --------------------------------------------------------------------------- #


@web_router.get("/lhpp")
def daftar_lhpp(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Lhpp, Penawaran, Client)
        .join(Penawaran, Penawaran.id == Lhpp.penawaran_id)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(Lhpp.deadline_at)
    )
    if not is_pusat(user):
        stmt = stmt.where(Lhpp.wilayah_id == user.wilayah_id)
    rows = db.execute(stmt).all()
    penawaran_lhpp = db.scalars(
        select(Penawaran).where(Penawaran.status == PenawaranStatus.SURAT_TUGAS)
    ).all()
    if not is_pusat(user):
        penawaran_lhpp = [p for p in penawaran_lhpp if p.wilayah_id == user.wilayah_id]
    return render(
        request,
        "lhpp_list.html",
        user=user,
        nav="lhpp",
        rows=rows,
        penawaran_lhpp=penawaran_lhpp,
        klien_map={c.id: c for c in db.scalars(select(Client)).all()},
    )


@web_router.post("/lhpp/siapkan/{penawaran_id}")
def siapkan_lhpp_ui(
    penawaran_id: int,
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: exec_api.siapkan_lhpp(penawaran_id, user=user, db=db),
        "/lhpp",
        msg="LHPP disiapkan, deadline dihitung 7 hari",
    )
    return resp


@web_router.post("/lhpp/{lhpp_id}/update")
def update_lhpp_ui(
    lhpp_id: int,
    tanggal_selesai: str = Form(""),
    catatan: str = Form(""),
    chk_lhpp: str = Form(""),
    chk_sklk3: str = Form(""),
    is_uploaded: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    lhpp = db.get(Lhpp, lhpp_id)
    if not lhpp:
        return back("/lhpp", err="Data LHPP tidak ditemukan")
    checklist = {
        "lhpp_external": chk_lhpp in {"on", "true", "1"},
        "sklk3": chk_sklk3 in {"on", "true", "1"},
    }
    payload = LhppUpdate(
        tanggal_selesai=date.fromisoformat(tanggal_selesai) if tanggal_selesai.strip() else None,
        catatan=catatan.strip(),
        checklist=checklist,
        is_uploaded=is_uploaded in {"on", "true", "1"},
    )
    resp, _ = run(
        lambda: exec_api.update_lhpp(lhpp_id, payload, user=user, db=db),
        f"/penawaran/{lhpp.penawaran_id}",
        msg="LHPP diperbarui",
    )
    return resp


@web_router.post("/sklk3/{penawaran_id}")
def submit_sklk3_ui(
    penawaran_id: int,
    nomor: str = Form(""),
    tanggal_muncul: str = Form(""),
    catatan: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = Sklk3In(
        nomor=nomor.strip(),
        tanggal_muncul=date.fromisoformat(tanggal_muncul) if tanggal_muncul.strip() else None,
        catatan=catatan.strip(),
    )
    resp, _ = run(
        lambda: exec_api.submit_sklk3(penawaran_id, payload, user=user, db=db),
        f"/penawaran/{penawaran_id}",
        msg="SKLK3 tersimpan",
    )
    return resp


@web_router.get("/keuangan")
def halaman_keuangan(
    request: Request,
    user: User = Depends(web_roles(UserRole.KEUANGAN, *ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Invoice, Penawaran, Client)
        .join(Penawaran, Penawaran.id == Invoice.penawaran_id)
        .join(Client, Client.id == Penawaran.client_id)
        .order_by(Invoice.created_at.desc())
        .limit(200)
    )
    if not is_pusat(user):
        stmt = stmt.where(Invoice.wilayah_id == user.wilayah_id)
    rows = db.execute(stmt).all()
    siap_invoice = db.scalars(
        select(Penawaran).where(
            Penawaran.status.in_([PenawaranStatus.SKLK3, PenawaranStatus.LHPP])
        )
    ).all()
    if not is_pusat(user):
        siap_invoice = [p for p in siap_invoice if p.wilayah_id == user.wilayah_id]
    return render(
        request,
        "keuangan.html",
        user=user,
        nav="keuangan",
        rows=rows,
        siap_invoice=siap_invoice,
        klien_map={c.id: c for c in db.scalars(select(Client)).all()},
    )


@web_router.post("/invoice/{penawaran_id}/terbit")
def terbitkan_invoice_ui(
    penawaran_id: int,
    tanggal: str = Form(""),
    nominal: str = Form(""),
    keterangan: str = Form(""),
    user: User = Depends(web_roles(UserRole.KEUANGAN, *ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = InvoiceIn(
        tanggal=date.fromisoformat(tanggal) if tanggal.strip() else None,
        nominal=money(nominal) if nominal.strip() else None,
        keterangan=keterangan.strip(),
    )
    resp, _ = run(
        lambda: exec_api.terbitkan_invoice(penawaran_id, payload, user=user, db=db),
        f"/penawaran/{penawaran_id}",
        msg="Invoice diterbitkan + notifikasi ke Grup Keuangan",
    )
    return resp


@web_router.post("/invoice/{invoice_id}/faktur")
def set_faktur_ui(
    invoice_id: int,
    faktur_nomor: str = Form(...),
    user: User = Depends(web_roles(UserRole.KEUANGAN, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: exec_api.set_faktur(invoice_id, InvoiceFakturIn(faktur_nomor=faktur_nomor.strip()), user=user, db=db),
        "/keuangan",
        msg="Faktur dicatat — penawaran selesai",
    )
    return resp


# --------------------------------------------------------------------------- #
# Master data, Wilayah, Pengguna
# --------------------------------------------------------------------------- #


@web_router.get("/master")
def halaman_master(
    request: Request,
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    from app.schemas.master import BidangOut, KategoriOut, ObjekOut

    kategori = master_api.list_kategori(db=db, user=user)
    bidang = master_api.list_bidang(db=db, user=user)
    objek = master_api.list_objek(db=db, user=user)
    return render(
        request,
        "master.html",
        user=user,
        nav="master",
        kategori=kategori,
        bidang=bidang,
        objek=objek,
        kat_map={k.id: k.nama for k in kategori},
        bid_map={b.id: b.nama for b in bidang},
    )


@web_router.post("/master/kategori")
def tambah_kategori(
    kode: str = Form(...),
    nama: str = Form(...),
    deskripsi: str = Form(""),
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: master_api.create_kategori(
            KategoriCreate(kode=kode.strip(), nama=nama.strip(), deskripsi=deskripsi.strip()),
            user=user,
            db=db,
        ),
        "/master",
        msg="Kategori ditambahkan",
    )
    return resp


@web_router.post("/master/bidang")
def tambah_bidang(
    kategori_id: int = Form(...),
    kode: str = Form(...),
    nama: str = Form(...),
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: master_api.create_bidang(
            BidangCreate(kategori_id=kategori_id, kode=kode.strip(), nama=nama.strip()), user=user, db=db
        ),
        "/master",
        msg="Bidang ditambahkan",
    )
    return resp


@web_router.post("/master/objek")
def tambah_objek(
    bidang_id: int = Form(...),
    kode: str = Form(...),
    nama: str = Form(...),
    satuan: str = Form("unit"),
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: master_api.create_objek(
            ObjekCreate(bidang_id=bidang_id, kode=kode.strip(), nama=nama.strip(), satuan=satuan.strip() or "unit"),
            user=user,
            db=db,
        ),
        "/master",
        msg="Objek ditambahkan",
    )
    return resp


@web_router.get("/wilayah")
def daftar_wilayah(
    request: Request,
    user: User = Depends(web_roles(*ADMIN_ROLES, UserRole.SPV, UserRole.KEUANGAN)),
    db: Session = Depends(get_db),
):
    rows = wilayah_api.list_wilayah(user=user, db=db)
    jumlah = {
        w.id: db.scalar(select(func.count(Client.id)).where(Client.wilayah_id == w.id, Client.is_active.is_(True)))
        for w in rows
    }
    return render(request, "wilayah_list.html", user=user, nav="wilayah", rows=rows, jumlah=jumlah)


@web_router.post("/wilayah")
def tambah_wilayah(
    kode: str = Form(...),
    nama: str = Form(...),
    provinsi: str = Form(""),
    kota: str = Form(""),
    kodepos: str = Form(""),
    alamat: str = Form(""),
    telepon: str = Form(""),
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    payload = WilayahCreate(
        kode=kode.strip().upper(),
        nama=nama.strip(),
        provinsi=provinsi.strip(),
        kota=kota.strip(),
        kodepos=kodepos.strip(),
        alamat=alamat.strip(),
        telepon=telepon.strip(),
    )
    resp, _ = run(lambda: wilayah_api.create_wilayah(payload, user=user, db=db), "/wilayah", msg="Wilayah dibuat")
    return resp


@web_router.post("/wilayah/{wilayah_id}/edit")
def edit_wilayah(
    wilayah_id: int,
    kode: str = Form(""),
    nama: str = Form(""),
    provinsi: str = Form(""),
    kota: str = Form(""),
    kodepos: str = Form(""),
    alamat: str = Form(""),
    telepon: str = Form(""),
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    payload = WilayahUpdate(
        kode=kode.strip().upper() or None,
        nama=nama.strip() or None,
        provinsi=provinsi.strip(),
        kota=kota.strip(),
        kodepos=kodepos.strip(),
        alamat=alamat.strip(),
        telepon=telepon.strip(),
    )
    resp, _ = run(
        lambda: wilayah_api.update_wilayah(wilayah_id, payload, user=user, db=db),
        "/wilayah",
        msg="Wilayah diperbarui",
    )
    return resp


@web_router.post("/wilayah/{wilayah_id}/hapus")
def hapus_wilayah(
    wilayah_id: int,
    user: User = Depends(web_roles(UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    resp, _ = run(
        lambda: wilayah_api.delete_wilayah(wilayah_id, user=user, db=db), "/wilayah", msg="Wilayah dinonaktifkan"
    )
    return resp


@web_router.get("/pengguna")
def daftar_pengguna(
    request: Request,
    role: str = "",
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    role_filter = UserRole(role) if role and role in {r.value for r in UserRole} else None
    rows = users_api.list_users(role=role_filter, user=user, db=db)
    return render(
        request,
        "pengguna_list.html",
        user=user,
        nav="pengguna",
        rows=rows,
        wilayah_map=_nama_wilayah(db),
        role=role,
        roles=[r.value for r in UserRole],
    )


@web_router.post("/pengguna/baru")
def tambah_pengguna(
    nama: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    wilayah_id: str = Form(""),
    no_hp: str = Form(""),
    jabatan: str = Form(""),
    telegram_chat_id: str = Form(""),
    user: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = UserCreate(
        nama=nama.strip(),
        email=email.strip(),
        password=password,
        role=UserRole(role),
        wilayah_id=to_int(wilayah_id, None),
        no_hp=no_hp.strip(),
        jabatan=jabatan.strip(),
        telegram_chat_id=telegram_chat_id.strip() or None,
    )
    resp, _ = run(lambda: users_api.create_user(payload, user=user, db=db), "/pengguna", msg="Pengguna dibuat")
    return resp


@web_router.post("/pengguna/{user_id}/edit")
def edit_pengguna(
    user_id: int,
    nama: str = Form(""),
    no_hp: str = Form(""),
    jabatan: str = Form(""),
    telegram_chat_id: str = Form(""),
    password: str = Form(""),
    is_active: str = Form(""),
    actor: User = Depends(web_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    payload = UserUpdate(
        nama=nama.strip() or None,
        no_hp=no_hp.strip(),
        jabatan=jabatan.strip(),
        telegram_chat_id=telegram_chat_id.strip() or None,
        password=password or None,
        is_active=is_active in {"on", "true", "1"},
    )
    resp, _ = run(
        lambda: users_api.update_user(user_id, payload, actor=actor, db=db), "/pengguna", msg="Pengguna diperbarui"
    )
    return resp
