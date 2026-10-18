from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PicCreate(BaseModel):
    nama: str
    no_hp: str = ""
    email: str = ""
    telegram_chat_id: str | None = None
    wilayah_id: int | None = None
    keahlian: str = ""
    is_aktif: bool = True


class PicOut(PicCreate):
    id: int

    class Config:
        from_attributes = True


class BookingCreate(BaseModel):
    penawaran_id: int
    pic_id: int
    tanggal_tugas: date
    catatan: str = ""


class BookingResponse(BaseModel):
    aksi: str = Field(pattern="^(APPROVE|RESCHEDULE)$")
    tanggal_usulan: date | None = None
    alasan: str = ""


class BookingOut(BaseModel):
    id: int
    penawaran_id: int
    pic_id: int
    tanggal_tugas: date
    tanggal_usulan: date | None
    status: str
    catatan: str

    class Config:
        from_attributes = True


class LhppUpdate(BaseModel):
    tanggal_selesai: date | None = None
    is_uploaded: bool | None = None
    bukti_screenshot_base64: str | None = None
    catatan: str | None = None
    checklist: dict | None = None


class Sklk3In(BaseModel):
    nomor: str = ""
    tanggal_muncul: date | None = None
    catatan: str = ""


class InvoiceIn(BaseModel):
    tanggal: date | None = None
    nominal: Decimal | None = None
    keterangan: str = ""


class InvoiceFakturIn(BaseModel):
    faktur_nomor: str
