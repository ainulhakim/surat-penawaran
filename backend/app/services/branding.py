"""Branding aplikasi: nilai default dari `.env`, dapat ditimpa dari halaman /pengaturan.

Disimpan di tabel `app_settings` (key-value) dengan cache singkat agar tidak
menambah query di setiap request.
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AppSetting

BRAND_KEYS = ("brand_name", "brand_subtitle", "brand_footer", "brand_doc_title")

_KEYS_FALLBACK = {
    "brand_name": lambda: settings.BRAND_NAME,
    "brand_subtitle": lambda: settings.BRAND_SUBTITLE,
    "brand_footer": lambda: settings.BRAND_FOOTER,
    "brand_doc_title": lambda: settings.BRAND_DOC_TITLE or settings.BRAND_NAME,
}

_CACHE: dict = {"at": 0.0, "data": None}
_TTL_SECONDS = 20.0


def defaults() -> dict[str, str]:
    data = {k: fn() for k, fn in _KEYS_FALLBACK.items()}
    if not data.get("brand_doc_title"):
        data["brand_doc_title"] = data["brand_name"]
    return data


def invalidate() -> None:
    _CACHE["data"] = None
    _CACHE["at"] = 0.0


def get_brand(force: bool = False) -> dict[str, str]:
    """Ambil branding efektif (default `.env` ditimpa nilai dari DB bila ada)."""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["at"]) < _TTL_SECONDS:
        return _CACHE["data"]

    data = defaults()
    try:
        db = SessionLocal()
        try:
            for row in db.scalars(select(AppSetting)).all():
                if row.key in data and (row.value or "").strip():
                    data[row.key] = row.value.strip()
        finally:
            db.close()
    except Exception:  # DB belum siap (mis. saat startup) — pakai default saja
        pass

    if not data.get("brand_doc_title"):
        data["brand_doc_title"] = data["brand_name"]
    _CACHE.update(at=now, data=data)
    return data


def simpan_brand(db: Session, nilai: dict[str, str], user_id: int | None) -> dict[str, str]:
    """Simpan branding. Nilai kosong = hapus override (kembali ke default `.env`)."""
    for key in BRAND_KEYS:
        if key not in nilai:
            continue
        value = (nilai.get(key) or "").strip()
        row = db.get(AppSetting, key)
        if row is None:
            if value:
                db.add(AppSetting(key=key, value=value, updated_by=user_id))
        elif value:
            row.value = value
            row.updated_by = user_id
        else:
            db.delete(row)
    db.commit()
    invalidate()
    return get_brand(force=True)
