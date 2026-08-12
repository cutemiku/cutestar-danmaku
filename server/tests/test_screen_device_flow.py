from httpx import AsyncClient

from app import store
from app.database import session_factory


async def test_screen_device_request_and_approve_flow(client: AsyncClient, activity, admin_token: str) -> None:
    aid = str(activity.id)
    device_id = "device-test-0001-abcdef123456"

    # 1. 大屏无 sk 连接（模拟 WS 无法在此测，直接走状态端点验证注册）
    # 先用 WS 端点注册：通过 store 直接注册更简单，这里模拟大屏首次连接注册 pending
    async with session_factory() as session:
        await store.screen_request_for_device(session, activity_id=activity.id, device_id=device_id, label="一号大屏")
        await session.commit()

    # 2. 查询状态应为 pending，且无 key
    status = await client.get(f"/api/v1/public/screen-keys/status?device_id={device_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"
    assert status.json()["key"] is None

    # 3. 待审批列表应包含该设备
    pending = await client.get(
        f"/api/v1/activities/{aid}/screen-keys/pending", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert pending.status_code == 200
    assert any(k["device_id"] == device_id for k in pending.json())

    # 4. 批准后状态为 approved 且返回明文 sk
    approved = await client.post(
        f"/api/v1/activities/{aid}/screen-keys/approve/{device_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approved.status_code == 200
    sk = approved.json()["key"]
    assert sk and len(sk) >= 32

    # 5. 大屏再次查询：approved，但首次查询返回明文密钥（burn-after-reading）
    status2 = await client.get(f"/api/v1/public/screen-keys/status?device_id={device_id}")
    assert status2.status_code == 200
    assert status2.json()["status"] == "approved"
    assert status2.json()["key"] == sk

    # 6. 待审批列表清空
    pending2 = await client.get(
        f"/api/v1/activities/{aid}/screen-keys/pending", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert not any(k["device_id"] == device_id for k in pending2.json())


async def test_screen_request_status_unknown(client: AsyncClient) -> None:
    status = await client.get("/api/v1/public/screen-keys/status?device_id=no-such-device-0000")
    assert status.status_code == 200
    assert status.json()["status"] == "unknown"


async def test_screen_request_status_requires_device_id(client: AsyncClient) -> None:
    status = await client.get("/api/v1/public/screen-keys/status")
    assert status.status_code == 422  # 缺少必填参数


async def test_screen_key_burn_after_reading(client: AsyncClient, activity, admin_token: str) -> None:
    """批准后 sk 明文仅返回一次（burn-after-reading），重复查询不再泄露。"""
    aid = str(activity.id)
    device_id = "device-burn-test-001-abcdef"

    # 注册设备请求
    from app import store
    from app.database import session_factory
    async with session_factory() as session:
        await store.screen_request_for_device(session, activity_id=activity.id, device_id=device_id, label="burn测试")
        await session.commit()

    # 批准
    approved = await client.post(
        f"/api/v1/activities/{aid}/screen-keys/approve/{device_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approved.status_code == 200
    sk = approved.json()["key"]
    assert sk and len(sk) >= 32

    # 查询状态：approved，首次查询返回明文密钥（burn-after-reading）
    status1 = await client.get(f"/api/v1/public/screen-keys/status?device_id={device_id}")
    assert status1.status_code == 200
    assert status1.json()["status"] == "approved"
    assert status1.json()["key"] == sk

    # 再次查询：明文密钥已被清除
    status2 = await client.get(f"/api/v1/public/screen-keys/status?device_id={device_id}")
    assert status2.status_code == 200
    assert status2.json()["status"] == "approved"
    assert status2.json()["key"] == ""


async def test_screen_key_hash_not_in_admin_list(client: AsyncClient, activity, admin_token: str) -> None:
    """管理员列表和待审批列表均不应泄露 key_hash 或 key_plain。"""
    aid = str(activity.id)
    device_id = "device-hash-leak-test-001"

    from app import store
    from app.database import session_factory
    async with session_factory() as session:
        await store.screen_request_for_device(session, activity_id=activity.id, device_id=device_id, label="哈希测试")
        await session.commit()

    pending = await client.get(
        f"/api/v1/activities/{aid}/screen-keys/pending", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert pending.status_code == 200
    for item in pending.json():
        assert "key_hash" not in item
        assert "key_plain" not in item

