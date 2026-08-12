import os

os.environ["CUTESTAR_DATABASE_URL"] = "sqlite+aiosqlite:///./test_cutestar.db"
os.environ["CUTESTAR_REDIS_URL"] = ""
os.environ["CUTESTAR_JWT_SECRET"] = "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz"
os.environ["CUTESTAR_ADMIN_USERNAME"] = "admin"
os.environ["CUTESTAR_ADMIN_PASSWORD"] = "test-admin-pw"
os.environ["CUTESTAR_ADMIN_ENTRY_PATH"] = "test-control-123"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, text

from app import store
from app.database import engine, run_migrations, session_factory
from app.main import app
from app.seed import seed_admin


@pytest_asyncio.fixture(autouse=True)
async def fresh_db() -> None:
    async with engine.begin() as conn:
        # 列出并删除所有表（含 alembic_version 等 ORM 元数据之外的表）
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        for name in table_names:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    # 走迁移建表，与生产一致
    await run_migrations()
    await seed_admin()
    async with session_factory() as session:
        await store.create_activity(session, name="测试活动", public_code="MEET2026")
        await store.create_screen_key(
            session,
            activity_id=(await store.activity_by_code(session, "MEET2026")).id,
            key="test-screen-key-0000000000000000",
            label="测试大屏",
        )
        await session.commit()
    yield


@pytest_asyncio.fixture(autouse=True)
async def clear_ratelimit() -> None:
    """每个测试前清空限速器计数，避免测试间共享内存导致 429 误伤。"""
    from app import ratelimit

    ratelimit.admin_login_limiter._hits.clear()
    ratelimit.danmaku_limiter._hits.clear()
    ratelimit.join_limiter._hits.clear()
    ratelimit.ws_limiter._hits.clear()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def activity():
    async with session_factory() as session:
        return await store.activity_by_code(session, "MEET2026")


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "test-admin-pw"}
    )
    assert response.status_code == 200
    return response.json()["token"]
