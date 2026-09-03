from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import Student
from app.auth import ActorContext
from app.domain.audit_service import log_audit

# Fields a student can change immediately vs. fields that require staff verification.
PERMITTED_FIELDS = {"phone_number", "address_in_algeria", "email"}
SENSITIVE_FIELDS = {"university_id", "programme", "academic_year", "scholarship_status"}


def find_student(db: Session, query: str) -> Student | None:
    """Fuzzy-ish lookup by student number, phone, or name. Staff-facing search only."""
    return (
        db.query(Student)
        .filter(
            or_(
                Student.student_number.ilike(f"%{query}%"),
                Student.phone_number.ilike(f"%{query}%"),
                Student.full_name.ilike(f"%{query}%"),
            )
        )
        .first()
    )


def get_student_by_id(db: Session, student_id: str) -> Student | None:
    return db.query(Student).filter(Student.id == student_id).first()


def get_student_profile(db: Session, student_id: str, actor: ActorContext) -> Student | None:
    actor.require_self(student_id)
    if actor.actor_type == "staff":
        actor.require_permission("students.view")
    student = get_student_by_id(db, student_id)
    if student:
        log_audit(
            db,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            action="viewed_student_profile",
            entity_type="student",
            entity_id=student_id,
        )
    return student


def update_student_profile(
    db: Session, student_id: str, fields: dict, actor: ActorContext
) -> dict:
    """
    Non-sensitive fields (phone, address, email) are applied immediately.
    Sensitive fields (university, programme, scholarship status) are flagged
    for staff review rather than applied silently — mirrors the
    'pending_verification' pattern used for documents and academic results.
    """
    actor.require_self(student_id)
    student = get_student_by_id(db, student_id)
    if not student:
        raise ValueError("Student not found")

    applied, pending = {}, {}
    for key, value in fields.items():
        if key in PERMITTED_FIELDS:
            setattr(student, key, value)
            applied[key] = value
        elif key in SENSITIVE_FIELDS:
            pending[key] = value
        # unknown fields are silently ignored rather than raising —
        # the agent should never be able to write to arbitrary columns

    db.commit()

    log_audit(
        db,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        action="updated_student_profile",
        entity_type="student",
        entity_id=student_id,
        metadata={"applied": applied, "flagged_for_review": pending},
    )

    if pending:
        log_audit(
            db,
            actor_type="system",
            action="profile_change_pending_staff_review",
            entity_type="student",
            entity_id=student_id,
            metadata=pending,
        )

    return {"applied": applied, "pending_staff_review": pending}
