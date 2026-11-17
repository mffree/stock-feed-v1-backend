from typing import AsyncIterator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def normalize_database_url(raw: str) -> URL:
    """Turn Render's `postgres://...` URL into one SQLAlchemy's asyncpg driver accepts.

    - `postgres://` / `postgresql://` -> `postgresql+asyncpg://`
    - libpq's `sslmode=` query param -> asyncpg's `ssl=`
    Other URLs (e.g. `sqlite+aiosqlite://` in tests) pass through unchanged.

    No SSL param is needed for Render: asyncpg defaults to ssl="prefer", which
    uses SSL on the external URL and works without it on the internal one.
    """
    url = make_url(raw)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg" and "sslmode" in url.query:
        query = dict(url.query)
        query["ssl"] = query.pop("sslmode")
        url = url.set(query=query)
    return url


engine = create_async_engine(
    normalize_database_url(settings.database_url),
    pool_pre_ping=True,  # Render may drop idle connections
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Tests override this."""
    async with SessionLocal() as session:
        yield session
