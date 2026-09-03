"""
Every tool the agent can call. Claude decides WHICH tool to use; this module
decides WHETHER it's allowed to, by delegating straight to the domain services,
which enforce authorization themselves (ActorContext.require_self /
require_permission). There is no path here to raw SQL or arbitrary queries —
each function below is narrow and purpose-built, matching Section 6 of the
architecture doc.
"""
from sqlalchemy.orm import Session

from app.auth import ActorContext
from app.domain import student_service, document_service, academic_service, welfare_service

# --- Tool schemas passed to the Claude API (Messages API `tools` param) ---

TOOL_SCHEMAS = [
    {
        "name": "get_student_profile",
        "description": "Fetch the authenticated student's own profile (university, programme, contact info, status). Only ever returns the caller's own record.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_student_profile",
        "description": "Update the student's own profile. Non-sensitive fields (phone_number, email, address_in_algeria) apply immediately. Sensitive fields (university_id, programme, academic_year, scholarship_status) are flagged for staff review instead of applied directly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "Key-value pairs of fields to update, e.g. {\"phone_number\": \"+213...\"}",
                }
            },
            "required": ["fields"],
        },
    },
    {
        "name": "get_documents",
        "description": "List all documents the student has submitted, with their verification status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_missing_documents",
        "description": "List required document types the student has not yet submitted.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_academic_records",
        "description": "Fetch the student's academic results across semesters, each labeled verified/pending_verification/rejected. Never state an average without calling this first.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_academic_result",
        "description": "Submit academic results for a semester after the student has confirmed extracted/provided course marks are correct. Always lands as pending_verification, never verified automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "semester_label": {"type": "string", "description": "e.g. 'Semester 2 2025-2026'"},
                "course_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "course": {"type": "string"},
                            "mark": {"type": "number"},
                            "credits": {"type": "number"},
                        },
                        "required": ["course", "mark"],
                    },
                },
            },
            "required": ["semester_label", "course_results"],
        },
    },
    {
        "name": "record_welfare_case",
        "description": "Log a welfare/administrative issue the student has raised (accommodation, financial, academic, health, administrative, other). This ONLY creates an open case for staff to act on — it can never resolve, escalate, or make a decision about the issue. Always tell the student a human will follow up.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["accommodation", "financial", "academic", "health", "administrative", "other"],
                },
                "description": {"type": "string", "description": "The issue in the student's own words / a faithful summary"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            },
            "required": ["category", "description", "severity"],
        },
    },
]


def dispatch_tool_call(
    db: Session, tool_name: str, tool_input: dict, actor: ActorContext, channel: str
) -> dict:
    """Routes a Claude tool-use request to the actual domain service call."""

    if tool_name == "get_student_profile":
        student = student_service.get_student_profile(db, actor.actor_id, actor)
        if not student:
            return {"error": "Student not found"}
        return {
            "student_number": student.student_number,
            "full_name": student.full_name,
            "university": student.university.name if student.university else None,
            "programme": student.programme,
            "academic_year": student.academic_year,
            "status": student.status,
            "phone_number": student.phone_number,
            "email": student.email,
        }

    if tool_name == "update_student_profile":
        return student_service.update_student_profile(
            db, actor.actor_id, tool_input.get("fields", {}), actor
        )

    if tool_name == "get_documents":
        docs = document_service.get_documents(db, actor.actor_id, actor)
        return {
            "documents": [
                {
                    "type": d.document_type.name if d.document_type else "unknown",
                    "status": d.status,
                    "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None,
                }
                for d in docs
            ]
        }

    if tool_name == "get_missing_documents":
        missing = document_service.get_missing_documents(db, actor.actor_id, actor)
        return {"missing_documents": missing}

    if tool_name == "get_academic_records":
        results = academic_service.get_academic_records(db, actor.actor_id, actor)
        return {
            "results": [
                {
                    "semester": r.semester_label,
                    "status": r.status,
                    "overall_average": float(r.overall_average) if r.overall_average is not None else None,
                }
                for r in results
            ]
        }

    if tool_name == "submit_academic_result":
        result = academic_service.submit_academic_result(
            db,
            actor.actor_id,
            tool_input["semester_label"],
            tool_input["course_results"],
            source_document_id=None,
            actor=actor,
        )
        return {
            "status": result.status,
            "calculated_average": float(result.overall_average) if result.overall_average is not None else None,
        }

    if tool_name == "record_welfare_case":
        case = welfare_service.record_welfare_case(
            db,
            actor.actor_id,
            category=tool_input["category"],
            description=tool_input["description"],
            severity=tool_input["severity"],
            created_via=channel,
            actor=actor,
        )
        return {"case_id": case.id, "status": case.status}

    return {"error": f"Unknown tool: {tool_name}"}
