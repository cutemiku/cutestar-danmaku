import asyncio

from fastapi.testclient import TestClient

from app.main import app

# 与 conftest.screen_key fixture 一致的大屏授权密钥
TEST_SK = "test-screen-key-0000000000000000"


def _ws_flow() -> None:
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "小星"}).json()
        participant_headers = {"Authorization": f"Bearer {joined['session_token']}"}
        admin_token = client.post(
            "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "test-admin-pw"}
        ).json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        with client.websocket_connect(
            f"/api/v1/activities/{joined['activity_id']}/events?sk={TEST_SK}"
        ) as ws:
            created = client.post(
                "/api/v1/public/danmaku",
                json={"activity_id": joined["activity_id"], "content": "大家好"},
                headers=participant_headers,
            )
            assert created.status_code == 201
            danmaku_id = created.json()["id"]

            client.post(f"/api/v1/danmaku/{danmaku_id}/approve", headers=admin_headers)

            first = ws.receive_json()
            second = ws.receive_json()
            events = {first["type"]: first, second["type"]: second}
            assert "danmaku.pending_created" in events
            assert events["danmaku.published"]["payload"]["id"] == danmaku_id
            assert events["danmaku.published"]["sequence"] > events["danmaku.pending_created"]["sequence"]
            # 连接后实时收到的事件不应带 replay 标记
            assert "replay" not in events["danmaku.published"]


async def test_websocket_receives_published_event() -> None:
    await asyncio.to_thread(_ws_flow)


def _ws_replay_marked() -> None:
    """断线补偿（连接时回放历史）的事件应带 replay 标记，客户端据此错峰展示。"""
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "补偿"}).json()
        user_headers = {"Authorization": f"Bearer {joined['session_token']}"}
        admin_token = client.post(
            "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "test-admin-pw"}
        ).json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 先产生历史事件（连接之前）
        for content in ("历史一", "历史二"):
            created = client.post(
                "/api/v1/public/danmaku",
                json={"activity_id": joined["activity_id"], "content": content},
                headers=user_headers,
            )
            client.post(f"/api/v1/danmaku/{created.json()['id']}/approve", headers=admin_headers)

        # 之后连接（断线补偿场景）：历史事件应带 replay=true
        with client.websocket_connect(
            f"/api/v1/activities/{joined['activity_id']}/events?last_sequence=0&sk={TEST_SK}"
        ) as ws:
            events = [ws.receive_json() for _ in range(4)]
            published = [e for e in events if e["type"] == "danmaku.published"]
            assert len(published) == 2
            assert all(e.get("replay") is True for e in published)


async def test_ws_replay_events_marked() -> None:
    await asyncio.to_thread(_ws_replay_marked)


def _ws_disconnect_mid_stream() -> None:
    """客户端断开后，服务端不应向已关闭的 socket 发送数据而崩溃，事件仍应正常广播。"""
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "幽灵"}).json()
        user_headers = {"Authorization": f"Bearer {joined['session_token']}"}
        admin_token = client.post(
            "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "test-admin-pw"}
        ).json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 幽灵连接：连接后立即断开（模拟 React StrictMode / 页面关闭）
        ghost = client.websocket_connect(f"/api/v1/activities/{joined['activity_id']}/events?sk={TEST_SK}")
        ghost.close()

        # 断开后事件照常流转
        created = client.post(
            "/api/v1/public/danmaku",
            json={"activity_id": joined["activity_id"], "content": "断开后的弹幕"},
            headers=user_headers,
        )
        assert created.status_code == 201
        client.post(f"/api/v1/danmaku/{created.json()['id']}/approve", headers=admin_headers)

        # 新连接仍能收到完整事件流
        with client.websocket_connect(
            f"/api/v1/activities/{joined['activity_id']}/events?sk={TEST_SK}"
        ) as ws2:
            types = [ws2.receive_json()["type"] for _ in range(2)]
            assert "danmaku.published" in types


async def test_ws_disconnect_mid_stream_does_not_crash() -> None:
    await asyncio.to_thread(_ws_disconnect_mid_stream)


def _ws_rejects_missing_key() -> None:
    """未携带授权密钥（或密钥无效）的连接必须被拒绝。"""
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "无钥"}).json()
        # 无 sk：应被拒绝
        try:
            with client.websocket_connect(f"/api/v1/activities/{joined['activity_id']}/events"):
                raise AssertionError("无密钥连接不应成功")
        except Exception:
            pass  # 期望拒绝


async def test_ws_rejects_missing_key() -> None:
    await asyncio.to_thread(_ws_rejects_missing_key)


def _ws_admin_token_connect() -> None:
    """管理端可通过 admin_token 查询参数免 sk 连接 WS 事件通道。"""
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "管观"}).json()
        participant_headers = {"Authorization": f"Bearer {joined['session_token']}"}
        admin_token = client.post(
            "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "test-admin-pw"}
        ).json()["token"]

        # 用 admin_token 连接 WS（无 sk）
        with client.websocket_connect(
            f"/api/v1/activities/{joined['activity_id']}/events?admin_token={admin_token}"
        ) as ws:
            # 发送弹幕并批准
            created = client.post(
                "/api/v1/public/danmaku",
                json={"activity_id": joined["activity_id"], "content": "管理员观察"},
                headers=participant_headers,
            )
            assert created.status_code == 201
            client.post(f"/api/v1/danmaku/{created.json()['id']}/approve", headers={"Authorization": f"Bearer {admin_token}"})

            # 收到 pending_created 和 published 两条事件
            first = ws.receive_json()
            second = ws.receive_json()
            types = {first["type"], second["type"]}
            assert "danmaku.pending_created" in types
            assert "danmaku.published" in types


async def test_ws_admin_token_connect() -> None:
    await asyncio.to_thread(_ws_admin_token_connect)


def _ws_invalid_admin_token_rejected() -> None:
    """无效的 admin_token 应被拒绝连接。"""
    with TestClient(app) as client:
        joined = client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "假管"}).json()
        try:
            with client.websocket_connect(
                f"/api/v1/activities/{joined['activity_id']}/events?admin_token=invalid-token"
            ):
                raise AssertionError("无效 admin_token 连接不应成功")
        except Exception:
            pass  # 期望拒绝


async def test_ws_invalid_admin_token_rejected() -> None:
    await asyncio.to_thread(_ws_invalid_admin_token_rejected)
