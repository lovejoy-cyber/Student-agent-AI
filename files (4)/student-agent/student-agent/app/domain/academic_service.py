from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AcademicResult, University, Student
from app.auth import ActorContext
from app.domain.audit_service import log_audit


def calculate_average(course_results: list[dict], grading_scale_config: dict | None = None) -> float:
    """
    Pure, deterministic calculation — never delegated to the LLM.
    course_results: [{"course": str, "mark": float, "credits": float}, ...]
    Weighted by credits if provided, otherwise a simple mean.
    """
    if not course_results:
        return 0.0

    has_credits = all(c.get("credits") for c in course_results)
    if has_credits:
        total_weighted = sum(c["mark"] * c["credits"] for c in course_results)
        total_credits = sum(c["credits"] for c in course_results)
        avg = total_weighted / total_credits if total_credits else 0.0
    else:
        avg = sum(c["mark"] for c in course_results) / len(course_results)

    rounding = (grading_scale_config or {}).get("rounding", "half_up")
    if rounding == "half_up":
        avg = round(avg + 1e-9, 2)  # tiny epsilon avoids banker's-rounding surprises
    return avg


def get_academic_records(db: Session, student_id: str, actor: ActorContext) -> list[AcademicResult]:
    actor.require_self(student_id)
    results = (
        db.query(AcademicResult)
        .filter(AcademicResult.student_id == student_id)
        .order_by(AcademicResult.created_at.desc())
        .all()
    )
    log_audit(
        db, actor_type=actor.actor_type, actor_id=actor.actor_id,
        action="viewed_academic_records", entity_type="student", entity_id=student_id,
    )
    return results


def submit_academic_result(
    db: Session,
    student_id: str,
    semester_label: str,
    course_results: list[dict],
    source_document_id: str | None,
    actor: ActorContext,
) -> AcademicResult:
    """Always lands as pending_verification — never auto-verified."""
    actor.require_self(student_id)

    student = db.query(Student).filter(Student.id == student_id).first()
    university = (
        db.query(University).filter(University.id == student.university_id).first()
        if student and student.university_id else None
    )
    grading_config = university.grading_scale_config if university else {}

    avg = calculate_average(course_results, grading_config)

    result = AcademicResult(
        student_id=student_id,
        semester_label=semester_label,
        status="pending_verification",
        overall_average=avg,
        course_results=course_results,
        source_document_id=source_document_id,
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    log_audit(
        db, actor_type=actor.actor_type, actor_id=actor.actor_id,
        action="submitted_academic_result", entity_type="academic_result", entity_id=result.id,
        metadata={"calculated_average": avg},
    )
    return result


def verify_academic_result(
    db: Session, result_id: str, decision: str, actor: ActorContext,
    corrected_course_results: list[dict] | None = None,
) -> AcademicResult:
    """Staff-only (academic_reviewer permission)."""
    actor.require_permission("academic.verify")

    result = db.query(AcademicResult).filter(AcademicResult.id == result_id).first()
    if not result:
        raise ValueError("Academic result not found")

    if corrected_course_results:
        student = db.query(Student).filter(Student.id == result.student_id).first()
        university = (
            db.query(University).filter(University.id == student.university_id).first()
            if student and student.university_id else None
        )
        result.course_results = corrected_course_results
        result.overall_average = calculate_average(
            corrected_course_results, university.grading_scale_config if university else {}
        )

    result.status = "verified" if decision == "approved" else "rejected"
    result.verified_by = actor.actor_id
    result.verified_at = datetime.utcnow()
    db.commit()

    log_audit(
        db, actor_type="staff", actor_id=actor.actor_id,
        action=f"{decision}_academic_result", entity_type="academic_result", entity_id=result_id,
        metadata={"final_average": float(result.overall_average) if result.overall_average else None},
    )
    return result
