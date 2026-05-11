
from pydantic import BaseModel, Field
from typing import List, Literal


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="The message text")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Full conversation history")


class Recommendation(BaseModel):
    name: str = Field(..., description="Assessment name from the SHL catalog")
    url: str = Field(..., description="Canonical URL from the SHL catalog")
    test_type: str = Field(..., description="Test type code(s), e.g. 'K', 'P', 'AKP'")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent's conversational reply")
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Empty when gathering context or refusing. 1-10 items when recommending."
    )
    end_of_conversation: bool = Field(
        default=False,
        description="True only when the agent considers the task complete"
    )


class HealthResponse(BaseModel):
    status: str = "ok"
