from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Penawaran, SuratTugas, Wilayah

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def roman_month(d: date) -> str:
    return ROMAN[d.month - 1]


def next_penawaran_number(db: Session, wilayah: Wilayah, when: date | None = None) -> tuple[int, int, str]:
    when = when or date.today()
    total = db.scalar(
        select(func.count(Penawaran.id)).where(
            Penawaran.wilayah_id == wilayah.id,
            Penawaran.tahun == when.year,
        )
    )
    urut = int(total or 0) + 1
    nomor = f"{urut:03d}/SP/{wilayah.kode}/{roman_month(when)}/{when.year}"
    return urut, when.year, nomor


def next_surat_tugas_number(db: Session, wilayah: Wilayah, when: date | None = None) -> str:
    when = when or date.today()
    total = db.scalar(
        select(func.count(SuratTugas.id)).where(
            SuratTugas.wilayah_id == wilayah.id,
            func.extract("year", SuratTugas.created_at) == when.year,
        )
    )
    urut = int(total or 0) + 1
    return f"{urut:03d}/ST/{wilayah.kode}/{roman_month(when)}/{when.year}"
