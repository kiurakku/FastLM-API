from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.database import SessionLocal
from app.models import WebhookRow
from app.settings import settings

log = logging.getLogger("fastlm.webhooks")


def sign_webhook_body(secret: str, body: bytes) -> str:
    """HMAC-SHA256 hex для заголовка X-Signature: sha256=<hex>."""
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


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
        sig = sign_webhook_body(settings.webhook_hmac_secret, body)
        headers = {"Content-Type": "application/json", "X-Signature": sig}
        delay = 1.0
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(h.url, content=body, headers=headers)
                if r.status_code < 500:
                    break
            except httpx.HTTPError:
                log.debug("webhook attempt %s failed", attempt, exc_info=True)
            await asyncio.sleep(delay)
            delay *= 2
