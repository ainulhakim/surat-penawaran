import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Bidang, Kategori, Objek, User, UserRole

logger = logging.getLogger(__name__)


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.role == UserRole.SUPERADMIN))
        if not existing:
            db.add(
                User(
                    nama=settings.SUPERADMIN_NAME,
                    email=settings.SUPERADMIN_EMAIL.lower(),
                    password_hash=hash_password(settings.SUPERADMIN_PASSWORD),
                    role=UserRole.SUPERADMIN,
                    jabatan="Super Admin Pusat",
                )
            )
            logger.info("superadmin dibuat: %s", settings.SUPERADMIN_EMAIL)

        if not db.scalar(select(Kategori)):
            kategori = Kategori(kode="K3", nama="Keselamatan & Kesehatan Kerja", deskripsi="Layanan K3")
            db.add(kategori)
            db.flush()
            bidang = Bidang(kategori_id=kategori.id, kode="K3-UMUM", nama="K3 Umum")
            db.add(bidang)
            db.flush()
            db.add(Objek(bidang_id=bidang.id, kode="OBJ-SURVEY", nama="Survey Lokasi", satuan="lokasi"))
            db.add(Objek(bidang_id=bidang.id, kode="OBJ-TRAINING", nama="Training K3", satuan="peserta"))
        db.commit()
    finally:
        db.close()
