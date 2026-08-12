import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _run_migrations_sync() -> None:
    """同步执行 alembic upgrade head（在线程中调用，避免在事件循环内嵌套 asyncio.run）。"""
    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")


async def run_migrations() -> None:
    """应用数据库迁移：旧库自动升级到最新结构（替代 create_all）。"""
    await asyncio.to_thread(_run_migrations_sync)


async def dispose_db() -> None:
    await engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
