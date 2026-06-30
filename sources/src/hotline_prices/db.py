"""PostgreSQL access layer: DB creation + SQLAlchemy async CRUD."""

import logging
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy_utils import create_database, database_exists

from .models_db import Config

logger = logging.getLogger(__name__)

_session_factory: async_sessionmaker | None = None


def create_db_if_not_exists(sync_url: str) -> None:
    """Create the PostgreSQL database if it does not exist.

    Table creation and migrations are handled exclusively by Alembic.
    """
    logger.info("Checking database existence")
    if not database_exists(sync_url):
        logger.info("Database not found, creating")
        create_database(sync_url)
        logger.info("Database created")


def init_db(async_url: str) -> None:
    """Initialise the async engine and session factory."""
    global _session_factory
    engine = create_async_engine(async_url)
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)


def get_session() -> AsyncSession:
    """Return a new async session from the factory."""
    return _session_factory()


async def config_create(data: dict) -> UUID:
    """Insert a new config row and return its UUID."""
    async with get_session() as session:
        result = await session.execute(
            insert(Config).values(data=data).returning(Config.id)
        )
        await session.commit()
        return result.scalar_one()


async def config_get(config_id: UUID) -> dict | None:
    """Return the config data dict, or None if not found."""
    async with get_session() as session:
        result = await session.execute(
            select(Config.data).where(Config.id == config_id)
        )
        row = result.scalar_one_or_none()
        return dict(row) if row is not None else None


async def config_update(config_id: UUID, data: dict) -> bool:
    """Overwrite config data. Returns True if a row was updated."""
    async with get_session() as session:
        result = await session.execute(
            update(Config)
            .where(Config.id == config_id)
            .values(data=data)
            .returning(Config.id)
        )
        await session.commit()
        return result.scalar_one_or_none() is not None
