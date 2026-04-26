from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app import redis_client as redis_mod
from app.database import dispose_engine, init_db
from app.routers import admin, completions
from app.settings import settings

log = logging.getLogger("fastlm")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    redis_mod.client = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    if redis_mod.client:
        await redis_mod.client.close()
        redis_mod.client = None
    await dispose_engine()


app = FastAPI(title=settings.api_title, version="1.0.0", lifespan=lifespan)

app.include_router(admin.router)
app.include_router(completions.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "fastlm"}
