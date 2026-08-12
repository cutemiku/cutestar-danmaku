from httpx import AsyncClient

from app.ratelimit import admin_login_limiter, danmaku_limiter, join_limiter, ws_limiter


async def test_admin_login_rate_limited(client: AsyncClient) -> None:
    admin_login_limiter.reset("127.0.0.1")
    for _ in range(20):
        await client.post(
            "/api/v1/auth/admin/login/test-control-123",
            json={"username": "admin", "password": "wrong"},
        )
    response = await client.post(
        "/api/v1/auth/admin/login/test-control-123",
        json={"username": "admin", "password": "test-admin-pw"},
    )
    assert response.status_code == 429
    admin_login_limiter.reset("127.0.0.1")


async def test_danmaku_rate_limited(client: AsyncClient, activity) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "限速侠"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    danmaku_limiter.reset(f"p:{joined['participant_id']}")
    danmaku_limiter.reset("127.0.0.1")
    for _ in range(5):
        await client.post(
            "/api/v1/public/danmaku",
            json={"activity_id": joined["activity_id"], "content": "限速测试"},
            headers=headers,
        )
    response = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "超限"},
        headers=headers,
    )
    assert response.status_code == 429
    danmaku_limiter.reset(f"p:{joined['participant_id']}")
    danmaku_limiter.reset("127.0.0.1")


async def test_join_rate_limited(client: AsyncClient) -> None:
    join_limiter.reset("127.0.0.1")
    for _ in range(3):
        await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "批量"})
    response = await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "超限"})
    assert response.status_code == 429
    join_limiter.reset("127.0.0.1")
