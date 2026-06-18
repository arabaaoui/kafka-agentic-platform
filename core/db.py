"""Async SQLAlchemy engine + session factory.

Usage (FastAPI dependency):
    async with get_session() as session:
        result = await session.execute(select(Mission).where(...))

Alembic uses DATABASE_URL_SYNC (synchronous psycopg2 URL) for migrations.
Runtime uses DATABASE_URL (asyncpg).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://platform:platform@localhost:5432/platform")

_engine = create_async_engine(
    _DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "").lower() in ("1", "true"),
)


def get_engine() -> AsyncEngine:
    """Return the global async engine instance."""
    return _engine


_SessionLocal = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager yielding an async DB session with automatic rollback on error."""
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the connection pool — call during application shutdown."""
    await _engine.dispose()
