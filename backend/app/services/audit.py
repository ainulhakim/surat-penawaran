from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | str = "",
    detail: str = "",
    ip_address: str = "",
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        wilayah_id=user.wilayah_id if user else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        detail=detail,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
