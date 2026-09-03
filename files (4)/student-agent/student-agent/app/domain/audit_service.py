from sqlalchemy.orm import Session

from app.models import AuditLog


def log_audit(
    db: Session,
    actor_type: str,
    action: str,
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """
    Every mutating action anywhere in the system should call this.
    actor_type: 'student' | 'staff' | 'agent' | 'system'
    """
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        log_metadata=metadata or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
