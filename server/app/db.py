import ssl

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


def database_options(database_url: str, transport: str = "auto") -> tuple:
    url = make_url(database_url)
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    url = url.set(drivername="postgresql+asyncpg")
    neon = bool(url.host and url.host.endswith((".neon.tech", ".neon.build")))
    websocket = transport == "websocket" or (transport == "auto" and neon)
    if websocket and not neon:
        raise ValueError("WebSocket database transport requires a Neon host")
    query = dict(url.query)
    mode = query.pop("sslmode", query.pop("ssl", None))
    # libpq's channel_binding isn't an asyncpg connect argument. TLS below
    # verifies Neon certificates; WSS also verifies the server hostname.
    query.pop("channel_binding", None)
    url = url.set(query=query)
    if websocket:
        from .neon import connect

        async def creator():
            return await connect(url)

        return url, {"async_creator": creator}
    connect_args = {}
    if neon or mode in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl"] = ssl.create_default_context()
    elif mode:
        connect_args["ssl"] = mode
    return url, {"connect_args": connect_args}


settings = get_settings()
url, options = database_options(settings.database_url, settings.database_transport)
engine = create_async_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, **options)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


MIGRATIONS = [
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS mode VARCHAR(10) DEFAULT 'manual'",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS kind VARCHAR(20) DEFAULT 'application'",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS meta JSON DEFAULT '{}'",
]


async def init_db():
    from . import models  # noqa: F401  registers tables

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all never alters existing tables; add columns introduced after the first deploy
        for stmt in MIGRATIONS:
            await conn.execute(text(stmt))


__all__ = ["AsyncSession", "Base", "SessionLocal", "engine", "get_db", "init_db"]
