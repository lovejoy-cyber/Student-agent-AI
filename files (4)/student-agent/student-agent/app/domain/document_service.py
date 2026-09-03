from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Document, DocumentType
from app.auth import ActorContext
from app.domain.audit_service import log_audit

# In the MVP, "required documents" is a fixed list per student rather than the
# full 'applies_to' rule engine in the architecture doc's document_types table.
# This keeps the first working slice simple; extend get_missing_documents()
# once you have more than one programme's requirements to model.
DEFAULT_REQUIRED_DOCUMENT_NAMES = [
    "Attestation d'inscription",
    "Transcript",
    "Passport copy",
    "Certified Zimsec certificate",
]


def get_documents(db: Session, student_id: str, actor: ActorContext) -> list[Document]:
    actor.require_self(student_id)
    if actor.actor_type == "staff":
        actor.require_permission("documents.view")
    docs = db.query(Document).filter(Document.student_id == student_id).all()
    log_audit(
        db, actor_type=actor.actor_type, actor_id=actor.actor_id,
        action="viewed_documents", entity_type="student", entity_id=student_id,
    )
    return docs


def get_missing_documents(db: Session, student_id: str, actor: ActorContext) -> list[str]:
    actor.require_self(student_id)
    submitted_types = {
        d.document_type.name
        for d in db.query(Document).filter(
            Document.student_id == student_id,
            Document.status.in_(["submitted", "pending_verification", "verified"]),
        ).all()
        if d.document_type
    }
    return [name for name in DEFAULT_REQUIRED_DOCUMENT_NAMES if name not in submitted_types]


def submit_document(
    db: Session,
    student_id: str,
    document_type_name: str,
    storage_path: str,
    original_filename: str,
    submitted_via: str,
    actor: ActorContext,
) -> Document:
    actor.require_self(student_id)

    doc_type = db.query(DocumentType).filter(DocumentType.name == document_type_name).first()
    if not doc_type:
        doc_type = DocumentType(name=document_type_name, required=True)
        db.add(doc_type)
        db.commit()
        db.refresh(doc_type)

    document = Document(
        student_id=student_id,
        document_type_id=doc_type.id,
        storage_path=storage_path,
        original_filename=original_filename,
        status="submitted",
        submitted_via=submitted_via,
        submitted_at=datetime.utcnow(),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_audit(
        db, actor_type=actor.actor_type, actor_id=actor.actor_id,
        action="submitted_document", entity_type="document", entity_id=document.id,
        metadata={"document_type": document_type_name, "via": submitted_via},
    )
    return document


def verify_document(
    db: Session, document_id: str, decision: str, actor: ActorContext, notes: str = ""
) -> Document:
    """Staff-only. decision: 'approved' | 'rejected'."""
    actor.require_permission("documents.view")
    if not actor.has_permission("documents.view"):
        raise PermissionError("Not authorized to verify documents")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError("Document not found")

    document.status = "verified" if decision == "approved" else "rejected"
    document.reviewed_by = actor.actor_id
    document.reviewed_at = datetime.utcnow()
    db.commit()

    log_audit(
        db, actor_type="staff", actor_id=actor.actor_id,
        action=f"{decision}_document", entity_type="document", entity_id=document_id,
        metadata={"notes": notes},
    )
    return document
