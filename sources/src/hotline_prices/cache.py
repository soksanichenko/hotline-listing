"""Redis cache wrapper with JSON serialisation."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class Cache:
    """Thin async Redis wrapper that stores values as JSON strings."""

    def __init__(self, redis_url: str, ttl: int = 3600) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl

    async def get(self, key: str) -> Any | None:
        """Return deserialised value or None on cache miss."""
        raw = await self._redis.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any) -> None:
        """Serialise and store value with the configured TTL."""
        await self._redis.set(key, json.dumps(value), ex=self._ttl)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.aclose()
