import asyncio

from sqlalchemy import select

from . import store
from .config import settings
from .database import run_migrations, session_factory
from .db_models import ActivityRow, AdminRow
from .security import hash_password


async def seed_admin() -> None:
    """按环境变量播种初始管理员；未配置 CUTESTAR_ADMIN_PASSWORD 时跳过。"""
    if not settings.admin_password:
        print("CUTESTAR_ADMIN_PASSWORD 未设置，跳过管理员初始化")
        return
    async with session_factory() as session:
        if await store.admin_by_username(session, settings.admin_username) is not None:
            return
        session.add(AdminRow(username=settings.admin_username, password_hash=hash_password(settings.admin_password)))
        await session.commit()
        print(f"已创建管理员 {settings.admin_username}")


async def seed_demo_activity() -> None:
    async with session_factory() as session:
        exists = await session.scalar(select(ActivityRow).where(ActivityRow.public_code == "MEET2026"))
        if exists is not None:
            print("演示活动 MEET2026 已存在，跳过")
            return
        session.add(ActivityRow(name="春日分享会", public_code="MEET2026"))
        await session.commit()
        print("已创建演示活动 MEET2026")


async def run() -> None:
    await run_migrations()
    await seed_admin()
    await seed_demo_activity()


if __name__ == "__main__":
    asyncio.run(run())
