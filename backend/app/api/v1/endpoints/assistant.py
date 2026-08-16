from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    city: str = "Pune"
    conversation_history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str
    confidence_score: float
    data_sources: list[str]
    map_data: dict | None
    supporting_evidence: list[dict]
    reasoning_trace: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI assistant not configured — set ANTHROPIC_API_KEY",
        )

    from app.agents.assistant_agent import AssistantAgent

    agent = AssistantAgent(session=session, city=request.city)
    return await agent.respond(
        message=request.message,
        history=[(m.role, m.content) for m in request.conversation_history],
        user_role=current_user.role.value,
    )
