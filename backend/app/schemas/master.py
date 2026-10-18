from pydantic import BaseModel, Field


class KategoriCreate(BaseModel):
    kode: str
    nama: str
    deskripsi: str = ""
    is_active: bool = True


class BidangCreate(BaseModel):
    kategori_id: int
    kode: str
    nama: str
    is_active: bool = True


class ObjekCreate(BaseModel):
    bidang_id: int
    kode: str
    nama: str
    satuan: str = "unit"
    is_active: bool = True


class KategoriOut(BaseModel):
    id: int
    kode: str
    nama: str
    deskripsi: str
    is_active: bool

    class Config:
        from_attributes = True


class BidangOut(BaseModel):
    id: int
    kategori_id: int
    kode: str
    nama: str
    is_active: bool

    class Config:
        from_attributes = True


class ObjekOut(BaseModel):
    id: int
    bidang_id: int
    kode: str
    nama: str
    satuan: str
    is_active: bool

    class Config:
        from_attributes = True
