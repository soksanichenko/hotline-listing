"""SQLAlchemy ORM models (used by Alembic for autogenerate)."""

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column


class Base(DeclarativeBase):
    pass


class Config(Base):
    """User price-watch config stored as JSONB."""

    __tablename__ = "configs"

    id: MappedColumn[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    data: MappedColumn[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{\"products\": []}'::jsonb"),
    )
    created_at: MappedColumn[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: MappedColumn[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
