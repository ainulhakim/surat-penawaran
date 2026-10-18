from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class MeResponse(BaseModel):
    id: int
    nama: str
    email: str
    role: str
    wilayah_id: int | None = None
    wilayah_nama: str | None = None
    has_ttd: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
