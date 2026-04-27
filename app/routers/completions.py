from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from hookify import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session, verify_api_key
from app.plugins_setup import plugin_registry
from app.schemas import ChatCompletionRequest
from app.services.quota import check_minute_quota, monthly_token_usage
from app.services.request_log import persist_request_log
from app.services.tokens import count_messages_prompt_tokens, count_text_tokens
from app.services.webhooks import dispatch_webhook
from app.settings import settings

router = APIRouter(tags=["completions"])


def _last_user_text(messages: Any) -> str:
    last = ""
    if isinstance(messages, list):
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                last = str(m.get("content") or "")
    return last


@router.post("/v1/chat/completions", response_model=None)
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
                                error_payload = {"error": {"message": err}}
                                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
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
                    raw_messages = ctx.body.get("messages")
                    msgs = raw_messages if isinstance(raw_messages, list) else []
                    last = _last_user_text(msgs)
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
                    raw_messages = ctx.body.get("messages")
                    msgs = raw_messages if isinstance(raw_messages, list) else []
                    pt = count_messages_prompt_tokens(msgs)
                    ct = count_text_tokens(assistant) if assistant else 1
                    await persist_request_log(user_id, body.model, pt, ct, latency_ms)

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
        msgs = ctx.body.get("messages") if isinstance(ctx.body.get("messages"), list) else []
        last = _last_user_text(msgs)
        reply = (
            f"[FastLM mock] Модель «{body.model}» отримала: {last[:500]!r}. "
            "Задайте OPENAI_API_KEY для реального виклику OpenAI."
        )
        pt = count_messages_prompt_tokens(msgs)
        ct = count_text_tokens(reply)
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
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
            },
        }

    data = plugin_registry.run_after(ctx, data)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    usage = data.get("usage") or {}
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    await persist_request_log(user_id, body.model, pt, ct, latency_ms)
    return data
