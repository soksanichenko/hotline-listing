"""PostgreSQL access layer: DB creation + SQLAlchemy async CRUD."""

import logging
from uuid import UUID

from sqlalchemy import delete, insert, select, update
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


async def config_create(data: dict, owner_discord_user_id: str | None = None) -> UUID:
    """Insert a new config row and return its UUID."""
    async with get_session() as session:
        result = await session.execute(
            insert(Config)
            .values(data=data, owner_discord_user_id=owner_discord_user_id)
            .returning(Config.id)
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


async def config_get_owner(config_id: UUID) -> tuple[bool, str | None]:
    """Return (exists, owner_discord_user_id). owner is None for legacy/unowned rows."""
    async with get_session() as session:
        result = await session.execute(
            select(Config.owner_discord_user_id).where(Config.id == config_id)
        )
        row = result.one_or_none()
        if row is None:
            return False, None
        return True, row[0]


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


async def config_delete(config_id: UUID) -> bool:
    """Delete a config row. Returns True if a row was deleted."""
    async with get_session() as session:
        result = await session.execute(
            delete(Config).where(Config.id == config_id).returning(Config.id)
        )
        await session.commit()
        return result.scalar_one_or_none() is not None


async def configs_list_for_owner(owner_discord_user_id: str) -> list[dict]:
    """Return configs owned by the given Discord user, newest first."""
    async with get_session() as session:
        result = await session.execute(
            select(Config.id, Config.data, Config.updated_at)
            .where(Config.owner_discord_user_id == owner_discord_user_id)
            .order_by(Config.updated_at.desc())
        )
        return [
            {
                "id": row.id,
                "product_count": len(row.data.get("products", [])),
                "updated_at": row.updated_at,
            }
            for row in result
        ]
