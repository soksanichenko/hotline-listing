import fakeredis
import pytest
from hotline_prices.cache import Cache


@pytest.fixture
def cache(monkeypatch) -> Cache:
    instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "hotline_prices.cache.aioredis.from_url", lambda *a, **k: instance
    )
    return Cache("redis://fake", ttl=60)


async def test_get_missing_key_returns_none(cache: Cache):
    assert await cache.get("missing") is None


async def test_set_then_get_roundtrips_json(cache: Cache):
    await cache.set("key", {"a": 1, "b": [1, 2, 3]})
    assert await cache.get("key") == {"a": 1, "b": [1, 2, 3]}


async def test_set_applies_configured_ttl(monkeypatch):
    instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "hotline_prices.cache.aioredis.from_url", lambda *a, **k: instance
    )
    cache = Cache("redis://fake", ttl=120)
    await cache.set("key", "value")
    ttl = await instance.ttl("key")
    assert 0 < ttl <= 120


async def test_close_does_not_raise(cache: Cache):
    await cache.close()


async def test_set_ttl_override_beats_configured_ttl(monkeypatch):
    instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "hotline_prices.cache.aioredis.from_url", lambda *a, **k: instance
    )
    cache = Cache("redis://fake", ttl=3600)
    await cache.set("key", "value", ttl=1800)
    ttl = await instance.ttl("key")
    assert 0 < ttl <= 1800
