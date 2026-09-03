import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Numeric, ForeignKey, Boolean, JSON, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class University(Base):
    __tablename__ = "universities"
    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    city = Column(String)
    # e.g. {"scale": 20, "pass_mark": 10, "rounding": "half_up"}
    grading_scale_config = Column(JSON, default=dict)

    students = relationship("Student", back_populates="university")


class Student(Base):
    __tablename__ = "students"
    id = Column(String, primary_key=True, default=gen_uuid)
    student_number = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    whatsapp_id = Column(String, unique=True, nullable=True)
    email = Column(String, nullable=True)

    university_id = Column(String, ForeignKey("universities.id"), nullable=True)
    programme = Column(String, nullable=True)
    academic_year = Column(String, nullable=True)  # e.g. "L2", "L3"

    address_in_algeria = Column(String, nullable=True)
    scholarship_status = Column(String, nullable=True)

    status = Column(String, default="active")  # active | graduated | withdrawn | suspended
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    university = relationship("University", back_populates="students")
    documents = relationship("Document", back_populates="student")
    academic_results = relationship("AcademicResult", back_populates="student")
    welfare_cases = relationship("WelfareCase", back_populates="student")


class DocumentType(Base):
    __tablename__ = "document_types"
    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)  # "Transcript", "Attestation d'inscription", etc.
    required = Column(Boolean, default=True)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    document_type_id = Column(String, ForeignKey("document_types.id"), nullable=False)

    storage_path = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)

    # submitted -> pending_verification -> verified | rejected | needs_correction | expired
    status = Column(String, default="submitted")
    submitted_via = Column(String, default="web")  # web | whatsapp | staff_upload
    submitted_at = Column(DateTime, default=datetime.utcnow)

    extracted_fields = Column(JSON, nullable=True)
    extraction_confidence = Column(Numeric, nullable=True)

    reviewed_by = Column(String, ForeignKey("staff_users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="documents")
    document_type = relationship("DocumentType")


class AcademicResult(Base):
    __tablename__ = "academic_results"
    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    semester_label = Column(String, nullable=False)  # "Semester 2 2025-2026"

    status = Column(String, default="draft")  # draft|pending_verification|verified|rejected
    overall_average = Column(Numeric, nullable=True)
    course_results = Column(JSON, nullable=True)  # [{course, mark, credits}, ...]

    source_document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    verified_by = Column(String, ForeignKey("staff_users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="academic_results")


class WelfareCase(Base):
    __tablename__ = "welfare_cases"
    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)

    category = Column(String, nullable=False)  # accommodation|financial|academic|health|administrative|other
    description = Column(Text, nullable=False)
    severity = Column(String, default="medium")  # low|medium|high|urgent
    status = Column(String, default="open")  # open|in_progress|awaiting_student|resolved|escalated

    assigned_staff_id = Column(String, ForeignKey("staff_users.id"), nullable=True)
    created_via = Column(String, default="web")  # web|whatsapp|staff_manual
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("Student", back_populates="welfare_cases")


class StaffUser(Base):
    __tablename__ = "staff_users"
    id = Column(String, primary_key=True, default=gen_uuid)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="staff")  # administrator|staff|academic_reviewer|welfare_officer|auditor
    status = Column(String, default="active")


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=True)
    channel = Column(String, default="web")  # web|whatsapp
    started_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=gen_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    sender_type = Column(String, nullable=False)  # student|staff|agent|system
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=gen_uuid)
    actor_type = Column(String, nullable=False)  # student|staff|agent|system
    actor_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    log_metadata = Column(JSON, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)


class PendingOTP(Base):
    """Short-lived OTP codes for student login and WhatsApp identity linking."""
    __tablename__ = "pending_otps"
    id = Column(String, primary_key=True, default=gen_uuid)
    phone_number = Column(String, nullable=False)
    code = Column(String, nullable=False)
    purpose = Column(String, default="login")  # login|whatsapp_link
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
