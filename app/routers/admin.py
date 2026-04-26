import json
import secrets
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.models import ApiKeyRow, RequestLogRow, WebhookRow
from app.schemas import KeyCreateIn, KeyCreateOut, WebhookCreateIn
from app.security import hash_api_key
from app.settings import settings

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(x_admin_secret: str | None) -> None:
    if not x_admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Невірний X-Admin-Secret")


@router.post("/keys", response_model=KeyCreateOut)
async def admin_create_key(
    body: KeyCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> KeyCreateOut:
    _require_admin(x_admin_secret)
    raw = f"sk-{secrets.token_urlsafe(24)}"
    kid = str(uuid.uuid4())
    row = ApiKeyRow(id=kid, key_hash=hash_api_key(raw), label=body.label)
    session.add(row)
    await session.commit()
    return KeyCreateOut(api_key=raw, id=kid)


@router.post("/webhooks")
async def admin_create_webhook(
    body: WebhookCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_admin(x_admin_secret)
    wid = str(uuid.uuid4())
    session.add(
        WebhookRow(id=wid, url=body.url, events=json.dumps(body.events, ensure_ascii=False))
    )
    await session.commit()
    return {"id": wid, "status": "created"}


@router.get("/usage")
async def admin_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: str,
    x_admin_secret: Annotated[str | None, Header()] = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    _require_admin(x_admin_secret)
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
