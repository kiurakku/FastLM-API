from __future__ import annotations

import time

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import redis_client as rc
from app.models import RequestLogRow
from app.settings import settings


async def monthly_token_usage(session: AsyncSession, user_id: str) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(
        func.coalesce(func.sum(RequestLogRow.prompt_tokens + RequestLogRow.completion_tokens), 0)
    ).where(RequestLogRow.user_id == user_id, RequestLogRow.created_at >= start)
    return int((await session.execute(q)).scalar_one())


async def check_minute_quota(user_id: str) -> None:
    if rc.client is None:
        raise RuntimeError("Redis не ініціалізовано")
    bucket = int(time.time() // 60)
    key = f"quota:{user_id}:{bucket}"
    n = await rc.client.incr(key)
    if n == 1:
        await rc.client.expire(key, 120)
    if n > settings.requests_per_minute:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Перевищено ліміт запитів на хвилину",
            headers={"Retry-After": "60"},
        )
