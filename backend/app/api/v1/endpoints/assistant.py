from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings
from app.schemas.base import APIResponse

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])

# The Gemini API requires every message role to be exactly "user" or
# "assistant" (mapped internally to Gemini's "model" role) — anything else
# (or empty content) is a malformed message that would otherwise reach the
# provider and fail there. Bounding content length and history length also
# keeps a single request from growing into an unbounded provider payload.
_MAX_MESSAGE_LENGTH = 4000
_MAX_HISTORY_MESSAGES = 50


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=_MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=_MAX_MESSAGE_LENGTH)
    city: str = "Pune"
    conversation_history: list[ChatMessage] = Field(
        default_factory=list, max_length=_MAX_HISTORY_MESSAGES
    )


class ChatResponse(BaseModel):
    answer: str
    confidence_score: float
    data_sources: list[str]
    map_data: dict | None
    supporting_evidence: list[dict]
    reasoning_trace: str


@router.post("/chat", response_model=APIResponse[ChatResponse])
async def chat_with_assistant(
    request: ChatRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[ChatResponse]:
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI assistant not configured — set GEMINI_API_KEY",
        )

    from app.agents.assistant_agent import AssistantAgent

    agent = AssistantAgent(session=session, city=request.city)
    try:
        result = await agent.respond(
            message=request.message,
            history=[(m.role, m.content) for m in request.conversation_history],
            user_role=current_user.role.value,
        )
        return APIResponse(data=result)
    except TimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e)
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
