from httpx import AsyncClient


async def test_danmaku_logs_include_ip_and_fingerprint(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "日志侠"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    body = {"activity_id": joined["activity_id"], "content": "记录我的来源", "device_fingerprint": "fp-log-12345"}
    created = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert created.status_code == 201

    logs = await client.get(
        f"/api/v1/activities/{joined['activity_id']}/danmaku-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert logs.status_code == 200
    data = logs.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["content"] == "记录我的来源"
    assert item["participant_id"] == joined["participant_id"]
    assert item["device_fingerprint"] == "fp-log-12345"
    assert item["ip_address"]  # 测试客户端有 host
    assert item["nickname"] == "日志侠"


async def test_danmaku_logs_require_admin(client: AsyncClient) -> None:
    response = await client.get("/api/v1/activities/00000000-0000-0000-0000-000000000000/danmaku-logs")
    assert response.status_code == 401


async def test_ban_participant_then_submission_rejected(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "待禁言"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    body = {"activity_id": joined["activity_id"], "content": "禁言前还能发"}

    before = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert before.status_code == 201

    # 永久禁言该参与者
    banned = await client.post(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        json={
            "target_type": "participant",
            "target_value": joined["participant_id"],
            "reason": "刷屏",
            "duration_minutes": None,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert banned.status_code == 201
    assert banned.json()["expires_at"] is None

    after = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "禁言后发不了"},
        headers=headers,
    )
    assert after.status_code == 403
    assert "禁言" in after.json()["detail"]


async def test_ban_temporary_returns_remaining_minutes(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "短禁"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}

    banned = await client.post(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        json={
            "target_type": "participant",
            "target_value": joined["participant_id"],
            "duration_minutes": 30,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert banned.status_code == 201
    assert banned.json()["expires_at"] is not None

    after = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "短禁测试"},
        headers=headers,
    )
    assert after.status_code == 403
    assert "剩余" in after.json()["detail"]


async def test_ban_by_device_fingerprint(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "指纹君"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    body = {"activity_id": joined["activity_id"], "content": "同设备再发", "device_fingerprint": "fp-dup-77777"}

    first = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert first.status_code == 201

    # 按设备指纹禁言
    banned = await client.post(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        json={"target_type": "fingerprint", "target_value": "fp-dup-77777", "duration_minutes": 60},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert banned.status_code == 201

    # 换一个参与者（新 token）但同设备指纹，仍被禁
    joined2 = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "同设备二号"})).json()
    headers2 = {"Authorization": f"Bearer {joined2['session_token']}"}
    body2 = {"activity_id": joined2["activity_id"], "content": "换个马甲", "device_fingerprint": "fp-dup-77777"}
    after = await client.post("/api/v1/public/danmaku", json=body2, headers=headers2)
    assert after.status_code == 403


async def test_ban_list_and_unban(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "解禁君"})).json()

    banned = await client.post(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        json={"target_type": "participant", "target_value": joined["participant_id"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert banned.status_code == 201
    ban_id = banned.json()["id"]

    listed = await client.get(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.status_code == 200
    assert any(b["id"] == ban_id for b in listed.json())

    removed = await client.delete(
        f"/api/v1/activities/{joined['activity_id']}/bans/{ban_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert removed.status_code == 204

    after_unban = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "解禁后能发了"},
        headers={"Authorization": f"Bearer {joined['session_token']}"},
    )
    assert after_unban.status_code == 201


async def test_ban_unknown_participant_404(client: AsyncClient, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "乱禁"})).json()
    response = await client.post(
        f"/api/v1/activities/{joined['activity_id']}/bans",
        json={
            "target_type": "participant",
            "target_value": "00000000-0000-0000-0000-000000000000",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_ban_requires_admin(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/activities/00000000-0000-0000-0000-000000000000/bans",
        json={"target_type": "participant", "target_value": "x"},
    )
    assert response.status_code == 401

async def test_screen_key_lifecycle(client: AsyncClient, activity, admin_token: str) -> None:
    aid = str(activity.id)
    # 申请
    created = await client.post(
        f"/api/v1/activities/{aid}/screen-keys",
        json={"label": "一号大屏"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["key"] and len(body["key"]) >= 32
    key_id = body["id"]

    # 列出（不应包含明文 key）
    listed = await client.get(
        f"/api/v1/activities/{aid}/screen-keys",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.status_code == 200
    assert any(k["id"] == key_id and k["key"] is None for k in listed.json())

    # 吊销后不可再用
    revoked = await client.delete(
        f"/api/v1/activities/{aid}/screen-keys/{key_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert revoked.status_code == 204

