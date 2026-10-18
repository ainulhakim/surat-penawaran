from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    nama: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
    wilayah_id: int | None = None
    no_hp: str = ""
    jabatan: str = ""
    telegram_chat_id: str | None = None


class UserUpdate(BaseModel):
    nama: str | None = None
    no_hp: str | None = None
    jabatan: str | None = None
    telegram_chat_id: str | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    wilayah_id: int | None = None


class UserOut(BaseModel):
    id: int
    nama: str
    email: str
    role: str
    wilayah_id: int | None
    no_hp: str
    jabatan: str
    telegram_chat_id: str | None
    is_active: bool
    has_ttd: bool = False

    class Config:
        from_attributes = True
