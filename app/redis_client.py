"""Глобальний async Redis-клієнт (ініціалізується в lifespan)."""

from __future__ import annotations

import redis.asyncio as redis

client: redis.Redis | None = None
