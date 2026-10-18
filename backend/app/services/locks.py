from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ClientLock, LockReason


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def active_lock(db: Session, client_id: int) -> ClientLock | None:
    lock = db.scalar(
        select(ClientLock).where(
            ClientLock.client_id == client_id,
            ClientLock.released_at.is_(None),
            ClientLock.expires_at > now_utc(),
        )
    )
    return lock


def create_lock(
    db: Session,
    client_id: int,
    penawaran_id: int,
    wilayah_id: int,
    user_id: int | None,
    nego: bool,
) -> ClientLock:
    days = settings.LOCK_DAYS_NEGO if nego else settings.LOCK_DAYS_NORMAL
    lock = ClientLock(
        client_id=client_id,
        penawaran_id=penawaran_id,
        wilayah_id=wilayah_id,
        locked_by=user_id,
        reason=LockReason.NEGO if nego else LockReason.NORMAL,
        expires_at=now_utc() + timedelta(days=days),
    )
    db.add(lock)
    return lock


def release_expired(db: Session) -> int:
    locks = db.scalars(
        select(ClientLock).where(
            ClientLock.released_at.is_(None),
            ClientLock.expires_at <= now_utc(),
        )
    ).all()
    for lock in locks:
        lock.released_at = now_utc()
        lock.release_note = "auto-release: masa berlaku habis"
    return len(locks)
