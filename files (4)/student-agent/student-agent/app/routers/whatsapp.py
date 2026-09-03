import hashlib
import hmac

from fastapi import APIRouter, Request, Query, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import Student
from app.auth import ActorContext, generate_otp, verify_otp
from app.whatsapp.client import send_whatsapp_text
from app.routers.agent import process_agent_message

router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])

# In-memory tracker for students mid-way through the "link my WhatsApp" OTP flow.
# For anything beyond a single-process prototype, move this to a DB table
# (e.g. reuse PendingOTP.purpose='whatsapp_link' plus a small state field).
_LINKING_STATE: dict[str, dict] = {}


@router.get("")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta calls this once when you register the webhook URL in the app dashboard."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.whatsapp_app_secret:
        # No app secret configured — allowed only in local/dev; set this in production.
        return settings.environment != "production"
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _extract_message(payload: dict) -> tuple[str, str] | None:
    """Returns (wa_id, text) for the first text message in a webhook payload, if any."""
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            return None
        msg = messages[0]
        wa_id = msg["from"]
        text = msg.get("text", {}).get("body", "")
        return wa_id, text
    except (KeyError, IndexError):
        return None


@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        return Response(status_code=401)

    payload = await request.json()
    extracted = _extract_message(payload)
    if not extracted:
        return {"status": "ignored"}  # e.g. delivery receipts, not a message

    wa_id, text = extracted
    student = db.query(Student).filter(Student.whatsapp_id == wa_id).first()

    if not student:
        _handle_unlinked_number(db, wa_id, text)
        return {"status": "ok"}

    actor = ActorContext(actor_type="student", actor_id=student.id)
    result = process_agent_message(db, actor, "whatsapp", None, text)
    send_whatsapp_text(wa_id, result.response)
    return {"status": "ok"}


def _handle_unlinked_number(db: Session, wa_id: str, text: str) -> None:
    """
    Identity-linking flow for a WhatsApp number not yet associated with a student.
    Step 1: ask for student number + phone on file.
    Step 2: verify OTP sent to that phone/email, then link whatsapp_id.
    This never guesses or auto-links based on name similarity alone.
    """
    state = _LINKING_STATE.get(wa_id, {"step": "awaiting_student_number"})

    if state["step"] == "awaiting_student_number":
        student = db.query(Student).filter(Student.student_number == text.strip()).first()
        if not student:
            send_whatsapp_text(
                wa_id,
                "I don't recognize that student number. Please reply with the exact student "
                "number on your embassy record so I can verify it's you.",
            )
            _LINKING_STATE[wa_id] = state
            return
        code = generate_otp(db, student.phone_number, purpose="whatsapp_link")
        # TODO: send `code` via SMS/email — for now, printed for local dev visibility.
        print(f"[DEV ONLY] WhatsApp-link OTP for {student.phone_number}: {code}")
        _LINKING_STATE[wa_id] = {"step": "awaiting_otp", "student_id": student.id, "phone": student.phone_number}
        send_whatsapp_text(wa_id, "Thanks — I've sent a verification code to your phone on file. Reply with that code.")
        return

    if state["step"] == "awaiting_otp":
        if verify_otp(db, state["phone"], text.strip(), purpose="whatsapp_link"):
            student = db.query(Student).filter(Student.id == state["student_id"]).first()
            student.whatsapp_id = wa_id
            db.commit()
            _LINKING_STATE.pop(wa_id, None)
            send_whatsapp_text(wa_id, f"You're verified, {student.full_name.split()[0]}! You can now ask me about your records anytime here.")
        else:
            send_whatsapp_text(wa_id, "That code didn't match or has expired. Please reply with your student number to try again.")
            _LINKING_STATE[wa_id] = {"step": "awaiting_student_number"}
        return
