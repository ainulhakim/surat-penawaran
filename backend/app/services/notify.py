import logging

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import NotificationTarget, User, UserRole

logger = logging.getLogger(__name__)


def telegram_targets(db: Session, tipe: str, wilayah_id: int | None) -> list[str]:
    rows = db.scalars(
        select(NotificationTarget).where(
            NotificationTarget.tipe == tipe,
            NotificationTarget.is_active.is_(True),
            or_(NotificationTarget.wilayah_id == wilayah_id, NotificationTarget.wilayah_id.is_(None)),
        )
    ).all()
    return [r.chat_id for r in rows if r.chat_id]


def user_chat_ids(db: Session, role: UserRole, wilayah_id: int | None) -> list[str]:
    users = db.scalars(
        select(User).where(
            User.role == role,
            User.is_active.is_(True),
            User.telegram_chat_id.is_not(None),
        )
    ).all()
    return [
        u.telegram_chat_id
        for u in users
        if u.telegram_chat_id and (wilayah_id is None or u.wilayah_id == wilayah_id or u.wilayah_id is None)
    ]


def send_telegram(text: str, chat_ids: list[str]) -> int:
    if not settings.TELEGRAM_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
        logger.info("telegram disabled, skip: %s", text[:80])
        return 0
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    sent = 0
    for chat_id in set(chat_ids):
        try:
            resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
            if resp.status_code == 200:
                sent += 1
            else:
                logger.warning("gagal kirim ke %s: %s", chat_id, resp.text[:200])
        except Exception as exc:  # pragma: no cover - network best effort
            logger.warning("error kirim telegram: %s", exc)
    return sent


def notify(
    db: Session,
    text: str,
    tipe: str,
    wilayah_id: int | None = None,
    roles: tuple[UserRole, ...] = (),
) -> int:
    targets = telegram_targets(db, tipe, wilayah_id)
    for role in roles:
        targets.extend(user_chat_ids(db, role, wilayah_id))
    return send_telegram(text, targets)
