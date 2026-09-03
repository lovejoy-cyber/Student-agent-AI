from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import ActorContext, get_current_actor
from app.models import Conversation, Message
from app.agent.router import classify_fast_path, handle_fast_path
from app.agent.claude_agent import run_agent_turn
from app.domain.audit_service import log_audit

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    conversation_id: str | None = None
    channel: str = "web"  # 'web' | 'whatsapp'
    content: str


class AgentMessageResponse(BaseModel):
    conversation_id: str
    route_taken: str  # 'fast_path' | 'agent_path'
    response: str


def _get_or_create_conversation(
    db: Session, conversation_id: str | None, student_id: str, channel: str
) -> Conversation:
    if conversation_id:
        convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if convo:
            return convo
    convo = Conversation(student_id=student_id, channel=channel)
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


def _load_history(db: Session, conversation_id: str, limit: int = 20) -> list[dict]:
    """Short-term conversational context only — never treated as authoritative
    student data (see claude_agent.py system prompt rule #1)."""
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .all()
    )
    history = []
    for m in msgs:
        role = "user" if m.sender_type == "student" else "assistant"
        history.append({"role": role, "content": m.content})
    return history


def process_agent_message(
    db: Session, actor: ActorContext, channel: str, conversation_id: str | None, content: str
) -> AgentMessageResponse:
    convo = _get_or_create_conversation(db, conversation_id, actor.actor_id, channel)

    db.add(Message(conversation_id=convo.id, sender_type="student", content=content))
    convo.last_message_at = datetime.utcnow()
    db.commit()

    intent = classify_fast_path(content)
    if intent:
        answer = handle_fast_path(db, intent, actor)
        route_taken = "fast_path"
    else:
        history = _load_history(db, convo.id)
        answer, tool_log = run_agent_turn(db, actor, channel, history[:-1] if history else [], content)
        route_taken = "agent_path"
        if tool_log:
            log_audit(
                db, actor_type="agent", actor_id=None,
                action="agent_tool_calls", entity_type="conversation", entity_id=convo.id,
                metadata={"tools": tool_log},
            )

    db.add(Message(conversation_id=convo.id, sender_type="agent", content=answer))
    db.commit()

    return AgentMessageResponse(conversation_id=convo.id, route_taken=route_taken, response=answer)


@router.post("/message", response_model=AgentMessageResponse)
def send_message(
    payload: AgentMessageRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_current_actor),
):
    return process_agent_message(db, actor, payload.channel, payload.conversation_id, payload.content)
