"""
Cheap keyword-based intent classification. Common status-check questions get
an instant, template-formatted answer straight from the database with NO LLM
call at all — this is what makes those feel instantaneous. Anything else
(free-form questions, welfare reports, guided document submission) falls
through to the full Claude tool-calling agent.
"""
from sqlalchemy.orm import Session

from app.auth import ActorContext
from app.domain import document_service, academic_service, student_service

FAST_PATH_PATTERNS = {
    "missing_documents": ["missing document", "what documents", "what's missing", "documents am i missing"],
    "my_average": ["my average", "what's my average", "my grade", "my gpa"],
    "my_records": ["show my record", "my profile", "my records", "current record"],
}


def classify_fast_path(text: str) -> str | None:
    lowered = text.lower()
    for intent, phrases in FAST_PATH_PATTERNS.items():
        if any(phrase in lowered for phrase in phrases):
            return intent
    return None


def handle_fast_path(db: Session, intent: str, actor: ActorContext) -> str:
    if intent == "missing_documents":
        missing = document_service.get_missing_documents(db, actor.actor_id, actor)
        if not missing:
            return "You've submitted everything required — no missing documents right now."
        return "You're missing: " + ", ".join(missing) + "."

    if intent == "my_average":
        results = academic_service.get_academic_records(db, actor.actor_id, actor)
        if not results:
            return "No academic results on file yet."
        latest = results[0]
        status_note = "" if latest.status == "verified" else f" ({latest.status.replace('_', ' ')})"
        return f"{latest.semester_label}: {latest.overall_average}/20{status_note}."

    if intent == "my_records":
        student = student_service.get_student_profile(db, actor.actor_id, actor)
        if not student:
            return "I couldn't find your record."
        uni = student.university.name if student.university else "not set"
        return (
            f"{student.full_name} — {uni}, {student.programme or 'programme not set'}, "
            f"{student.academic_year or ''}. Status: {student.status}."
        )

    return "Let me look into that for you."
