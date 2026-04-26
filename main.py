"""
FastLM API — OpenAI-сумісний шлюз з ключами, квотами Redis, логами та hookify-плагінами.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hookify import PluginRegistry, RequestContext
from hookify.plugins import AuditLogPlugin, PIIMaskPlugin, PromptInjectionPlugin

log = logging.getLogger("fastlm")
logging.basicConfig(level=logging.INFO)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    admin_secret: str
    webhook_hmac_secret: str = "dev-change-me"
    enabled_plugins: str = "audit,pii_mask,prompt_injection,cost_limit"
    default_monthly_token_budget: int = 1_000_000
    requests_per_minute: int = 60
    api_title: str = "FastLM API"


settings = Settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
redis_client: redis.Redis | None = None


class Base(DeclarativeBase):
    pass


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequestLogRow(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookRow(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    url: Mapped[str] = mapped_column(Text())
    events: Mapped[str] = mapped_column(Text())  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_plugin_registry_simple() -> PluginRegistry:
    reg = PluginRegistry()
    names = {x.strip() for x in settings.enabled_plugins.split(",") if x.strip()}
    if "pii_mask" in names:
        reg.register(PIIMaskPlugin())
    if "prompt_injection" in names:
        reg.register(PromptInjectionPlugin())
    if "audit" in names:
        reg.register(AuditLogPlugin(sink=lambda line: log.info("audit %s", line)))
    return reg


plugin_registry = build_plugin_registry_simple()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    if redis_client:
        await redis_client.close()
    await engine.dispose()


app = FastAPI(title=settings.api_title, version="1.0.0", lifespan=lifespan)


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


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def verify_api_key(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Потрібен Authorization: Bearer <api_key>")
    raw = authorization.split(" ", 1)[1].strip()
    digest = _hash_key(raw)
    q = select(ApiKeyRow).where(ApiKeyRow.key_hash == digest)
    row = (await session.execute(q)).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невірний API-ключ")
    return row.id


async def monthly_token_usage(session: AsyncSession, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(
        func.coalesce(func.sum(RequestLogRow.prompt_tokens + RequestLogRow.completion_tokens), 0)
    ).where(RequestLogRow.user_id == user_id, RequestLogRow.created_at >= start)
    return int((await session.execute(q)).scalar_one())


async def check_minute_quota(user_id: str) -> None:
    assert redis_client is not None
    bucket = int(time.time() // 60)
    key = f"quota:{user_id}:{bucket}"
    n = await redis_client.incr(key)
    if n == 1:
        await redis_client.expire(key, 120)
    if n > settings.requests_per_minute:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Перевищено ліміт запитів на хвилину",
            headers={"Retry-After": "60"},
        )


async def _persist_request_log(
    user_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
) -> None:
    async with SessionLocal() as session:
        session.add(
            RequestLogRow(
                id=str(uuid.uuid4()),
                user_id=user_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )
        )
        await session.commit()
    asyncio.create_task(
        dispatch_webhook(
            "request.completed",
            {
                "user_id": user_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
            },
        )
    )


async def dispatch_webhook(event: str, payload: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(WebhookRow))
        hooks = result.scalars().all()
    for h in hooks:
        try:
            evs = json.loads(h.events)
        except json.JSONDecodeError:
            continue
        if event not in evs:
            continue
        body = json.dumps({"event": event, "payload": payload}, ensure_ascii=False).encode("utf-8")
        sig = hmac.new(
            settings.webhook_hmac_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        headers = {"Content-Type": "application/json", "X-Signature": f"sha256={sig}"}
        delay = 1.0
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(h.url, content=body, headers=headers)
                if r.status_code < 500:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
            delay *= 2


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "fastlm"}


@app.post("/admin/keys", response_model=KeyCreateOut)
async def admin_create_key(
    body: KeyCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> KeyCreateOut:
    if not x_admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Невірний X-Admin-Secret")
    raw = f"sk-{secrets.token_urlsafe(24)}"
    kid = str(uuid.uuid4())
    row = ApiKeyRow(id=kid, key_hash=_hash_key(raw), label=body.label)
    session.add(row)
    await session.commit()
    return KeyCreateOut(api_key=raw, id=kid)


@app.post("/admin/webhooks")
async def admin_create_webhook(
    body: WebhookCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not x_admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Невірний X-Admin-Secret")
    wid = str(uuid.uuid4())
    session.add(
        WebhookRow(id=wid, url=body.url, events=json.dumps(body.events, ensure_ascii=False))
    )
    await session.commit()
    return {"id": wid, "status": "created"}


@app.get("/admin/usage")
async def admin_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: str,
    x_admin_secret: Annotated[str | None, Header()] = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    if not x_admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Невірний X-Admin-Secret")
    q = select(
        func.count(RequestLogRow.id),
        func.coalesce(func.sum(RequestLogRow.prompt_tokens), 0),
        func.coalesce(func.sum(RequestLogRow.completion_tokens), 0),
    ).where(RequestLogRow.user_id == user_id)
    if from_ts:
        q = q.where(RequestLogRow.created_at >= from_ts)
    if to_ts:
        q = q.where(RequestLogRow.created_at <= to_ts)
    cnt, pt, ct = (await session.execute(q)).one()
    return {"requests": int(cnt), "prompt_tokens": int(pt), "completion_tokens": int(ct)}


def _last_user_text(messages: Any) -> str:
    last = ""
    if isinstance(messages, list):
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                last = str(m.get("content") or "")
    return last


@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(verify_api_key)],
) -> dict[str, Any] | StreamingResponse:
    await check_minute_quota(user_id)
    used = await monthly_token_usage(session, user_id)
    if used >= settings.default_monthly_token_budget:
        asyncio.create_task(
            dispatch_webhook(
                "quota.exceeded",
                {"user_id": user_id, "used": used, "budget": settings.default_monthly_token_budget},
            )
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Вичерпано місячний бюджет токенів",
            headers={"Retry-After": str(86400)},
        )

    raw_body = body.model_dump()
    ctx = RequestContext(body=raw_body, user_id=user_id, model=body.model)
    plugin_registry.run_before(ctx)
    rej = ctx.extras.get("http_reject")
    if isinstance(rej, tuple) and len(rej) == 2:
        raise HTTPException(rej[1], detail=rej[0])

    if body.stream:

        async def sse() -> Any:
            assistant = ""
            t0 = time.perf_counter()
            completed = False
            try:
                if settings.openai_api_key:
                    async with httpx.AsyncClient(timeout=120.0) as http:
                        async with http.stream(
                            "POST",
                            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                            json=ctx.body,
                        ) as resp:
                            if resp.status_code >= 400:
                                err = (await resp.aread()).decode(errors="replace")
                                yield f"data: {json.dumps({'error': {'message': err}}, ensure_ascii=False)}\n\n"
                                return
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    payload = line[6:].strip()
                                    if payload == "[DONE]":
                                        yield "data: [DONE]\n\n"
                                        continue
                                    try:
                                        obj = json.loads(payload)
                                        ch0 = (obj.get("choices") or [{}])[0]
                                        delta = ch0.get("delta") or {}
                                        c = delta.get("content")
                                        if isinstance(c, str):
                                            assistant += c
                                    except json.JSONDecodeError:
                                        pass
                                yield line + "\n\n"
                    completed = True
                else:
                    last = _last_user_text(ctx.body.get("messages"))
                    reply = (
                        f"[FastLM mock] Модель «{body.model}» отримала: {last[:500]!r}. "
                        "Задайте OPENAI_API_KEY для реального виклику OpenAI."
                    )
                    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                    created = int(time.time())
                    chunk0 = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": ""},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk0, ensure_ascii=False)}\n\n"
                    step = 32
                    for i in range(0, len(reply), step):
                        part = reply[i : i + step]
                        assistant += part
                        chunk = {
                            "id": cid,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": body.model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": part},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.015)
                    final = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    completed = True
            finally:
                if completed:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    last_u = _last_user_text(ctx.body.get("messages"))
                    pt = min(50 + len(last_u) // 4, 500)
                    ct = min(max(len(assistant) // 4, 1), 3000)
                    await _persist_request_log(user_id, body.model, pt, ct, latency_ms)

        return StreamingResponse(sse(), media_type="text/event-stream")

    t0 = time.perf_counter()
    if settings.openai_api_key:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=ctx.body,
            )
            if r.status_code >= 400:
                raise HTTPException(r.status_code, detail=r.text)
            data = r.json()
    else:
        last = _last_user_text(ctx.body.get("messages"))
        reply = (
            f"[FastLM mock] Модель «{body.model}» отримала: {last[:500]!r}. "
            "Задайте OPENAI_API_KEY для реального виклику OpenAI."
        )
        data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": min(50 + len(last) // 4, 500),
                "completion_tokens": min(len(reply) // 4, 300),
                "total_tokens": 0,
            },
        }
        u = data["usage"]
        u["total_tokens"] = u["prompt_tokens"] + u["completion_tokens"]

    data = plugin_registry.run_after(ctx, data)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    usage = data.get("usage") or {}
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    await _persist_request_log(user_id, body.model, pt, ct, latency_ms)
    return data
