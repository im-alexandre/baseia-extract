from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://baseia:baseia@127.0.0.1:5432/baseia"
)


def database_url() -> str:
    return os.getenv("BASEIA_DATABASE_URL", DEFAULT_DATABASE_URL).strip()


engine: AsyncEngine = create_async_engine(
    database_url(),
    pool_pre_ping=True,
    pool_size=int(os.getenv("BASEIA_DATABASE_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("BASEIA_DATABASE_MAX_OVERFLOW", "20")),
)
SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def session_dependency() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
