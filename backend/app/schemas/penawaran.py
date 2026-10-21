from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ItemIn(BaseModel):
    kategori_id: int | None = None
    bidang_id: int | None = None
    objek_id: int | None = None
    uraian: str
    spesifikasi: str = ""
    qty: Decimal = Decimal("1")
    satuan: str = "unit"
    harga_satuan: Decimal = Decimal("0")
    is_nego: bool = False
    harga_nego: Decimal | None = None


class PenawaranCreate(BaseModel):
    client_id: int
    perihal: str = ""
    catatan: str = ""
    is_nego: bool = False
    items: list[ItemIn] = Field(default_factory=list)


class PenawaranUpdate(BaseModel):
    perihal: str | None = None
    catatan: str | None = None
    is_nego: bool | None = None
    items: list[ItemIn] | None = None


class ApprovalIn(BaseModel):
    aksi: str
    catatan: str = ""
    ttd_image_base64: str | None = None


class DealIn(BaseModel):
    tgl_po: date
    no_spk: str
    nilai_po: Decimal | None = None


class ItemOut(BaseModel):
    id: int
    kategori_id: int | None
    bidang_id: int | None
    objek_id: int | None
    uraian: str
    spesifikasi: str
    qty: Decimal
    satuan: str
    harga_satuan: Decimal
    subtotal: Decimal
    is_nego: bool
    harga_nego: Decimal | None

    class Config:
        from_attributes = True


class PenawaranOut(BaseModel):
    id: int
    nomor_surat: str
    status: str
    perihal: str
    is_nego: bool
    harga_total: Decimal
    valid_until: date | None
    client_id: int
    wilayah_id: int
    tgl_po: date | None = None
    no_spk: str = ""
    created_at: datetime
    items: list[ItemOut] = []

    class Config:
        from_attributes = True


class PenawaranRingkas(BaseModel):
    id: int
    wilayah_id: int | None = None
    nomor_surat: str
    status: str
    perihal: str
    nama_perusahaan: str
    kota: str
    harga_total: Decimal | None = None
    valid_until: date | None = None
    is_nego: bool = False
    # False = baris milik wilayah lain (isi rahasia dikosongkan; hanya nama + kota)
    akses_penuh: bool = True

    class Config:
        from_attributes = True
