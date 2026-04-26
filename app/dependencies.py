from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import ApiKeyRow
from app.security import hash_api_key


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
    digest = hash_api_key(raw)
    q = select(ApiKeyRow).where(ApiKeyRow.key_hash == digest)
    row = (await session.execute(q)).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невірний API-ключ")
    return row.id
