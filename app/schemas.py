from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-4o-mini"
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    stream: bool = False


class KeyCreateIn(BaseModel):
    label: str = ""


class KeyCreateOut(BaseModel):
    api_key: str = Field(description="Показується один раз")
    id: str


class WebhookCreateIn(BaseModel):
    url: str
    events: list[Literal["request.completed", "quota.exceeded"]]
