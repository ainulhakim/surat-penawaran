from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Surat Penawaran Multi Wilayah"
    ENV: str = "prod"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    ALGORITHM: str = "HS256"

    DATABASE_URL: str = "postgresql+psycopg://sp_user:sp_pass_change_me@db:5432/surat_penawaran"

    SUPERADMIN_EMAIL: str = "superadmin@suratpenawaran.id"
    SUPERADMIN_PASSWORD: str = "SuperAdmin2026!"
    SUPERADMIN_NAME: str = "Super Admin Pusat"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ENABLED: bool = False

    LOCK_DAYS_NORMAL: int = 15
    LOCK_DAYS_NEGO: int = 7
    LHPP_DEADLINE_DAYS: int = 7
    UPLOAD_DIR: str = "/app/uploads"
    AUTO_CREATE_TABLES: bool = True

    # Sesi UI (cookie HttpOnly). Set COOKIE_SECURE=true bila sudah lewat HTTPS (Cloudflare Tunnel).
    COOKIE_SECURE: bool = False
    COOKIE_NAME: str = "sp_session"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
