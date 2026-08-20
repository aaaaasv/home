from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.common.config import get_settings


def apply_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_pragmas(connection, connection_record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # handlers, the climate job and the ecoflow poll all write concurrently. without wal a reader
        # blocks a writer, and with the default zero busy timeout the loser raises immediately instead
        # of waiting — which the family sees as «Щось пішло не так» for no reason they can perceive
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


@lru_cache
def get_engine() -> AsyncEngine:
    engine = create_async_engine(get_settings().database_url)
    apply_sqlite_pragmas(engine)
    return engine


@lru_cache
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
