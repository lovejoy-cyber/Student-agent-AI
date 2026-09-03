from sqlalchemy.orm import Session

from app.models import WelfareCase
from app.auth import ActorContext
from app.domain.audit_service import log_audit

VALID_CATEGORIES = {"accommodation", "financial", "academic", "health", "administrative", "other"}
VALID_SEVERITIES = {"low", "medium", "high", "urgent"}


def record_welfare_case(
    db: Session,
    student_id: str,
    category: str,
    description: str,
    severity: str,
    created_via: str,
    actor: ActorContext,
) -> WelfareCase:
    """
    Always created as 'open'. The agent proposes category/severity but never
    sets status beyond 'open', never assigns staff, and never resolves —
    those are staff-only actions via update_welfare_case().
    """
    actor.require_self(student_id)

    category = category if category in VALID_CATEGORIES else "other"
    severity = severity if severity in VALID_SEVERITIES else "medium"

    case = WelfareCase(
        student_id=student_id,
        category=category,
        description=description,
        severity=severity,
        status="open",
        created_via=created_via,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    log_audit(
        db, actor_type=actor.actor_type, actor_id=actor.actor_id,
        action="recorded_welfare_case", entity_type="welfare_case", entity_id=case.id,
        metadata={"category": category, "severity": severity},
    )
    return case


def get_welfare_cases(db: Session, student_id: str, actor: ActorContext) -> list[WelfareCase]:
    actor.require_self(student_id)
    return db.query(WelfareCase).filter(WelfareCase.student_id == student_id).all()


def update_welfare_case(
    db: Session, case_id: str, actor: ActorContext,
    status: str | None = None, assigned_staff_id: str | None = None, notes: str | None = None,
) -> WelfareCase:
    """Staff-only. This is the ONLY path by which a case can be resolved/escalated/reassigned."""
    actor.require_permission("welfare.manage")

    case = db.query(WelfareCase).filter(WelfareCase.id == case_id).first()
    if not case:
        raise ValueError("Welfare case not found")

    if status:
        case.status = status
    if assigned_staff_id:
        case.assigned_staff_id = assigned_staff_id
    db.commit()

    log_audit(
        db, actor_type="staff", actor_id=actor.actor_id,
        action="updated_welfare_case", entity_type="welfare_case", entity_id=case_id,
        metadata={"status": status, "assigned_staff_id": assigned_staff_id, "notes": notes},
    )
    return case
