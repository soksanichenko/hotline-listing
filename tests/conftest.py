"""Shared test fixtures.

Test DB: a real PostgreSQL, spun up once per session via testcontainers
(the user explicitly wants db.py tested against real Postgres, not a mock).
Test Redis: fakeredis (in-memory, no container) — swapped in by monkeypatching
`aioredis.from_url` inside cache.py, since Cache always calls that internally.
Test HTTP: hotline.ua calls are mocked via httpx.MockTransport — swapped in by
monkeypatching `httpx.AsyncClient` inside app.py's lifespan.

`hotline_prices.app` reads `config.yaml` (path from CONFIG_PATH) at IMPORT
TIME, and database_url/redis_url have no env-var override (see config.py) —
so the test config.yaml pointing at the real Postgres container must exist,
and CONFIG_PATH must be set, before app.py is first imported. Do not import
`hotline_prices.app` at test-module top level; only via the `app_module`/
`client` fixtures below, so import order stays controlled.
"""

import json
from collections.abc import Iterator
from importlib import import_module

import fakeredis
import httpx
import pytest
import yaml
from testcontainers.community.postgres import PostgresContainer

_GRAPHQL_URL = "https://hotline.ua/svc/frontend-api/graphql"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Plain postgresql:// URL, matching AppConfig.database_url's expected form."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    dbname = postgres_container.dbname
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="session")
def app_config_path(tmp_path_factory: pytest.TempPathFactory, database_url: str) -> str:
    """Write a test config.yaml pointing at the test Postgres, set CONFIG_PATH."""
    path = tmp_path_factory.mktemp("config") / "config.yaml"
    path.write_text(
        yaml.dump({"database_url": database_url, "redis_url": "redis://fake"})
    )
    return str(path)


@pytest.fixture(scope="session")
def app_module(app_config_path: str, monkeypatch_session):
    """Import hotline_prices.app once, only after CONFIG_PATH is set."""
    monkeypatch_session.setenv("CONFIG_PATH", app_config_path)
    return import_module("hotline_prices.app")


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch (builtin `monkeypatch` is function-scoped)."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session", autouse=True)
def _db_schema(database_url: str) -> None:
    """Create the schema once per session via SQLAlchemy metadata (not Alembic —
    this tests db.py's CRUD logic against real Postgres semantics, not the
    migration chain itself)."""
    import sqlalchemy
    from hotline_prices.models_db import Base

    sync_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        Base.metadata.create_all(conn)
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_configs_table(database_url: str) -> Iterator[None]:
    """Truncate the configs table before each test for isolation."""
    import sqlalchemy

    sync_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("TRUNCATE TABLE configs"))
    engine.dispose()
    yield


@pytest.fixture(scope="session")
def db_ready(database_url: str) -> None:
    """Point db.py's session factory at the test Postgres, without importing app.py.

    Use this for db.py tests that don't need the full FastAPI app.
    """
    from hotline_prices import db

    async_url = database_url.replace("postgresql://", "postgresql+psycopg_async://", 1)
    db.init_db(async_url)


@pytest.fixture
def fake_redis(monkeypatch, app_module) -> fakeredis.aioredis.FakeRedis:
    """Make Cache() use an in-memory fake Redis instead of a real connection."""
    instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "hotline_prices.cache.aioredis.from_url", lambda *a, **k: instance
    )
    return instance


class FakeHotline:
    """Registers canned hotline.ua responses and serves them via httpx.MockTransport.

    Usage in a test:
        fake_hotline.set_chart(path, {"priceUAH": [["27.09.2026", 100]], ...})
        fake_hotline.set_page_html(url, "<html>...window.__NUXT__=...</html>")
    Unregistered paths/URLs get harmless defaults (empty chart / empty HTML),
    so tests that don't care about hotline.ua data still work.
    """

    def __init__(self) -> None:
        self._charts: dict[str, dict] = {}
        self._pages: dict[str, str] = {}

    def set_chart(self, path: str, payload: dict) -> None:
        self._charts[path] = payload

    def set_page_html(self, url: str, html: str) -> None:
        self._pages[url] = html

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == _GRAPHQL_URL:
            body = json.loads(request.content)
            path = body["variables"]["path"]
            chart = self._charts.get(
                path,
                {"priceUAH": [], "minPriceUAH": [], "priceUSD": [], "quantity": []},
            )
            return httpx.Response(200, json={"data": {"chart": chart}})
        html = self._pages.get(
            str(request.url), "<html><body>no nuxt payload</body></html>"
        )
        return httpx.Response(200, text=html)


@pytest.fixture
def fake_hotline(monkeypatch, app_module) -> FakeHotline:
    """Make the app's outbound HTTP client (_http) hit FakeHotline instead of the network."""
    fake = FakeHotline()
    transport = httpx.MockTransport(fake.handler)
    real_async_client = (
        httpx.AsyncClient
    )  # capture before patching — see module docstring
    monkeypatch.setattr(
        "hotline_prices.app.httpx.AsyncClient",
        lambda **kwargs: real_async_client(transport=transport),
    )
    return fake


@pytest.fixture
def client(app_module, fake_redis, fake_hotline):
    """FastAPI TestClient with real Postgres, fake Redis, and mocked hotline.ua HTTP."""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as test_client:
        yield test_client
