from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    ActorContext, get_current_actor, generate_otp, verify_otp, create_access_token,
)
from app.models import Student
from app.domain import student_service, document_service, academic_service

router = APIRouter(tags=["students"])


# --- Student OTP login ---

class OTPRequest(BaseModel):
    phone_number: str


class OTPVerify(BaseModel):
    phone_number: str
    code: str


@router.post("/auth/student/request-otp")
def request_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.phone_number == payload.phone_number).first()
    if not student:
        # Same response either way — don't leak whether a phone number is registered
        return {"message": "If this number is registered, a code has been sent."}
    code = generate_otp(db, payload.phone_number, purpose="login")
    # TODO: actually send `code` via SMS provider or WhatsApp template.
    # Left as a print for local dev so you can see it without an SMS integration wired up yet.
    print(f"[DEV ONLY] OTP for {payload.phone_number}: {code}")
    return {"message": "If this number is registered, a code has been sent."}


@router.post("/auth/student/verify-otp")
def verify_student_otp(payload: OTPVerify, db: Session = Depends(get_db)):
    if not verify_otp(db, payload.phone_number, payload.code, purpose="login"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    student = db.query(Student).filter(Student.phone_number == payload.phone_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    token = create_access_token("student", student.id)
    return {"access_token": token, "student_id": student.id}


# --- Student-facing REST (used by the web dashboard views, not just chat) ---

@router.get("/students/me/profile")
def get_my_profile(db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor)):
    student = student_service.get_student_profile(db, actor.actor_id, actor)
    if not student:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "student_number": student.student_number,
        "full_name": student.full_name,
        "university": student.university.name if student.university else None,
        "programme": student.programme,
        "status": student.status,
    }


@router.get("/students/me/documents")
def get_my_documents(db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor)):
    docs = document_service.get_documents(db, actor.actor_id, actor)
    return [{"type": d.document_type.name if d.document_type else None, "status": d.status} for d in docs]


@router.get("/students/me/academic-results")
def get_my_results(db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor)):
    results = academic_service.get_academic_records(db, actor.actor_id, actor)
    return [
        {"semester": r.semester_label, "status": r.status, "average": float(r.overall_average or 0)}
        for r in results
    ]


# --- Staff-facing ---

@router.get("/staff/search-students")
def search_students(
    q: str, db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor)
):
    actor.require_permission("students.view")
    student = student_service.find_student(db, q)
    if not student:
        return {"results": []}
    return {
        "results": [{
            "id": student.id,
            "student_number": student.student_number,
            "full_name": student.full_name,
            "university": student.university.name if student.university else None,
        }]
    }


class VerifyDocumentRequest(BaseModel):
    decision: str  # 'approved' | 'rejected'
    notes: str = ""


@router.post("/documents/{document_id}/verify")
def verify_document_endpoint(
    document_id: str, payload: VerifyDocumentRequest,
    db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor),
):
    try:
        doc = document_service.verify_document(db, document_id, payload.decision, actor, payload.notes)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"document_id": doc.id, "status": doc.status}


class VerifyAcademicResultRequest(BaseModel):
    decision: str  # 'approved' | 'rejected'
    corrected_course_results: list[dict] | None = None


@router.post("/academic-results/{result_id}/verify")
def verify_academic_result_endpoint(
    result_id: str, payload: VerifyAcademicResultRequest,
    db: Session = Depends(get_db), actor: ActorContext = Depends(get_current_actor),
):
    try:
        result = academic_service.verify_academic_result(
            db, result_id, payload.decision, actor, payload.corrected_course_results
        )
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "result_id": result.id,
        "status": result.status,
        "overall_average": float(result.overall_average or 0),
    }
