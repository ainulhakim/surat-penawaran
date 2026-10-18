from pydantic import BaseModel, Field


class WilayahBase(BaseModel):
    kode: str = Field(min_length=2, max_length=20)
    nama: str
    provinsi: str = ""
    kota: str = ""
    kodepos: str = ""
    alamat: str = ""
    telepon: str = ""
    is_active: bool = True


class WilayahCreate(WilayahBase):
    pass


class WilayahUpdate(BaseModel):
    kode: str | None = None
    nama: str | None = None
    provinsi: str | None = None
    kota: str | None = None
    kodepos: str | None = None
    alamat: str | None = None
    telepon: str | None = None
    is_active: bool | None = None


class WilayahOut(WilayahBase):
    id: int

    class Config:
        from_attributes = True
