import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PendingOTP

# --- Role -> permission map (mirrors roles/permissions/role_permissions tables
# from the full schema; kept as a Python dict here for MVP simplicity). ---
ROLE_PERMISSIONS = {
    "administrator": {"*"},
    "staff": {"students.view", "documents.view", "welfare.view", "followups.manage"},
    "academic_reviewer": {"students.view", "documents.view", "academic.verify"},
    "welfare_officer": {"students.view", "welfare.manage"},
    "auditor": {"audit.view", "students.view", "documents.view", "academic.view", "welfare.view"},
}


@dataclass
class ActorContext:
    actor_type: str  # 'student' | 'staff'
    actor_id: str
    role: str | None = None  # only set for staff

    def has_permission(self, permission: str) -> bool:
        if self.actor_type != "staff":
            return False
        perms = ROLE_PERMISSIONS.get(self.role or "", set())
        return "*" in perms or permission in perms

    def require_permission(self, permission: str):
        if not self.has_permission(permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")

    def require_self(self, student_id: str):
        """A student actor may only ever act on their own record."""
        if self.actor_type == "student" and self.actor_id != student_id:
            raise HTTPException(status_code=403, detail="Cannot access another student's record")


# --- JWT ---

def create_access_token(actor_type: str, actor_id: str, role: str | None = None) -> str:
    minutes = (
        settings.staff_token_expire_minutes
        if actor_type == "staff"
        else settings.student_token_expire_minutes
    )
    payload = {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> ActorContext:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return ActorContext(
        actor_type=payload["actor_type"],
        actor_id=payload["actor_id"],
        role=payload.get("role"),
    )


def get_current_actor(authorization: str | None = Header(default=None)) -> ActorContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    return decode_access_token(token)


# --- OTP (used for student login and WhatsApp identity linking) ---

def generate_otp(db: Session, phone_number: str, purpose: str = "login") -> str:
    code = "".join(random.choices(string.digits, k=6))
    entry = PendingOTP(
        phone_number=phone_number,
        code=code,
        purpose=purpose,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.add(entry)
    db.commit()
    # NOTE: actually sending this via SMS/WhatsApp is a separate integration
    # (e.g. an SMS provider, or the WhatsApp Cloud API for students already
    # linked). Wire that in app/whatsapp/client.py or an SMS client of your choice.
    return code


def verify_otp(db: Session, phone_number: str, code: str, purpose: str = "login") -> bool:
    entry = (
        db.query(PendingOTP)
        .filter(
            PendingOTP.phone_number == phone_number,
            PendingOTP.code == code,
            PendingOTP.purpose == purpose,
            PendingOTP.consumed.is_(False),
        )
        .order_by(PendingOTP.created_at.desc())
        .first()
    )
    if not entry or entry.expires_at < datetime.utcnow():
        return False
    entry.consumed = True
    db.commit()
    return True
