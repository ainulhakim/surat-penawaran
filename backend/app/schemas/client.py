from pydantic import BaseModel, EmailStr, Field


class ClientBase(BaseModel):
    nama_perusahaan: str = Field(min_length=2, max_length=200)
    no_telpon: str = ""
    email: str = ""
    pic: str = ""
    no_pic: str = ""
    alamat: str = ""
    kota: str = ""
    provinsi: str = ""
    kodepos: str = ""


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    nama_perusahaan: str | None = None
    no_telpon: str | None = None
    email: str | None = None
    pic: str | None = None
    no_pic: str | None = None
    alamat: str | None = None
    kota: str | None = None
    provinsi: str | None = None
    kodepos: str | None = None
    is_active: bool | None = None


class ClientOut(ClientBase):
    id: int
    wilayah_id: int | None = None
    is_active: bool = True
    lock_status: str = "FREE"
    lock_until: str | None = None
    # Wilayah yang sedang memegang lock (kalau ada)
    lock_wilayah_id: int | None = None
    lock_wilayah_nama: str | None = None
    # False = klien tidak bisa dipakai membuat penawaran baru (terkunci wilayah lain)
    can_quote: bool = True

    class Config:
        from_attributes = True


class ClientPublicOut(BaseModel):
    id: int
    nama_perusahaan: str
    kota: str
    provinsi: str
    lock_status: str = "FREE"

    class Config:
        from_attributes = True
