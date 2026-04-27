from __future__ import annotations

import asyncio
import uuid

from app.database import SessionLocal
from app.models import RequestLogRow
from app.services.webhooks import dispatch_webhook


async def persist_request_log(
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
