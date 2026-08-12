from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


async def test_join_submit_approve_flow(client: AsyncClient, activity, admin_token: str) -> None:
    joined = await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "小星"})
    assert joined.status_code == 200
    data = joined.json()
    headers = {"Authorization": f"Bearer {data['session_token']}"}

    created = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": data["activity_id"], "content": "大家好"},
        headers=headers,
    )
    assert created.status_code == 201
    danmaku = created.json()
    assert danmaku["status"] == "pending"

    queue = await client.get(
        f"/api/v1/activities/{data['activity_id']}/moderation-queue",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert queue.status_code == 200
    assert [item["id"] for item in queue.json()] == [danmaku["id"]]

    approved = await client.post(
        f"/api/v1/danmaku/{danmaku['id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "published"


async def test_join_unknown_activity_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/public/activities/NOPE/join", json={"nickname": "路人"})
    assert response.status_code == 404


async def test_submit_requires_participant_token(client: AsyncClient, activity) -> None:
    response = await client.post(
        "/api/v1/public/danmaku", json={"activity_id": str(activity.id), "content": "未授权"}
    )
    assert response.status_code == 401


async def test_moderation_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.get(f"/api/v1/activities/{activity.id}/moderation-queue")
    assert response.status_code == 401


async def test_control_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.post(
        f"/api/v1/activities/{activity.id}/controls", json={"action": "pause_submissions"}
    )
    assert response.status_code == 401


async def test_admin_login_rejects_bad_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/admin/login/test-control-123", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_admin_entry_hides_default_login_route(client: AsyncClient) -> None:
    old_route = await client.post(
        "/api/v1/auth/admin/login", json={"username": "admin", "password": "test-admin-pw"}
    )
    wrong_entry = await client.get("/api/v1/auth/admin/entry/wrong-control-123")
    valid_entry = await client.get("/api/v1/auth/admin/entry/test-control-123")
    assert old_route.status_code == 404
    assert wrong_entry.status_code == 404
    assert valid_entry.status_code == 204


async def test_paused_activity_rejects_submission(
    client: AsyncClient, activity, admin_token: str
) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "小林"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    body = {"activity_id": joined["activity_id"], "content": "先暂停再发"}

    paused = await client.post(
        f"/api/v1/activities/{activity.id}/controls",
        json={"action": "pause_submissions"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert paused.status_code == 200

    response = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert response.status_code == 409


async def test_idempotency_key_deduplicates(client: AsyncClient, activity) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "阿泽"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}", "Idempotency-Key": "same-key-123"}
    body = {"activity_id": joined["activity_id"], "content": "只发一次"}

    first = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    second = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_reject_endpoint(client: AsyncClient, activity, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "小满"})).json()
    created = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "这条不过审"},
        headers={"Authorization": f"Bearer {joined['session_token']}"},
    )
    danmaku_id = created.json()["id"]

    rejected = await client.post(
        f"/api/v1/danmaku/{danmaku_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


async def test_activity_stats(client: AsyncClient, activity, admin_token: str) -> None:
    # 初始：0 已上墙
    stats = await client.get(f"/api/v1/activities/{activity.id}/stats")
    assert stats.status_code == 200
    assert stats.json()["published_count"] == 0
    assert stats.json()["online_count"] >= 0

    # 提交并批准一条弹幕
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "统计员"})).json()
    created = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "统计测试"},
        headers={"Authorization": f"Bearer {joined['session_token']}"},
    )
    await client.post(
        f"/api/v1/danmaku/{created.json()['id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # 已上墙 = 1
    stats = await client.get(f"/api/v1/activities/{activity.id}/stats")
    assert stats.json()["published_count"] == 1


async def _submit(client: AsyncClient, activity_id: str, session_token: str, content: str, color: str | None = None):
    body: dict = {"activity_id": activity_id, "content": content}
    if color is not None:
        body["color"] = color
    return await client.post(
        "/api/v1/public/danmaku",
        json=body,
        headers={"Authorization": f"Bearer {session_token}"},
    )


async def test_danmaku_uses_default_color(client: AsyncClient, activity, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "色测"})).json()
    created = await _submit(client, joined["activity_id"], joined["session_token"], "默认颜色")
    assert created.status_code == 201
    assert created.json()["color"] == "#FFFFFF"  # 默认固定色


async def test_custom_color_ignored_when_disabled(client: AsyncClient, activity) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "色测"})).json()
    created = await _submit(client, joined["activity_id"], joined["session_token"], "自定义被忽略", "#FF0000")
    assert created.status_code == 201
    assert created.json()["color"] == "#FFFFFF"  # 未开启自定义，回落默认色


async def test_custom_color_used_when_enabled(
    client: AsyncClient, activity, admin_token: str
) -> None:
    # 开启自定义颜色
    response = await client.put(
        f"/api/v1/activities/{activity.id}/danmaku-settings",
        json={"color_mode": "fixed", "default_color": "#FFFFFF", "allow_custom_color": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200

    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "色测"})).json()
    created = await _submit(client, joined["activity_id"], joined["session_token"], "自定义颜色", "#00FF00")
    assert created.status_code == 201
    assert created.json()["color"] == "#00FF00"


async def test_random_mode_uses_palette(client: AsyncClient, activity, admin_token: str) -> None:
    await client.put(
        f"/api/v1/activities/{activity.id}/danmaku-settings",
        json={"color_mode": "random", "default_color": "#FFFFFF", "allow_custom_color": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "色测"})).json()
    created = await _submit(client, joined["activity_id"], joined["session_token"], "随机颜色")
    assert created.status_code == 201
    from app.store import RANDOM_PALETTE

    assert created.json()["color"] in RANDOM_PALETTE


async def test_danmaku_settings_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.put(
        f"/api/v1/activities/{activity.id}/danmaku-settings",
        json={"color_mode": "fixed", "default_color": "#FFFFFF", "allow_custom_color": True},
    )
    assert response.status_code == 401


async def test_invalid_color_rejected(client: AsyncClient, activity) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "色测"})).json()
    created = await _submit(client, joined["activity_id"], joined["session_token"], "非法颜色", "red")
    assert created.status_code == 422


async def test_overlay_settings(client: AsyncClient, activity, admin_token: str) -> None:
    # 初始默认值
    public = await client.get("/api/v1/public/activities/MEET2026")
    assert public.json()["overlay_font_size"] == 28
    assert public.json()["overlay_font"] == "Segoe UI"

    # 管理员更新
    response = await client.put(
        f"/api/v1/activities/{activity.id}/overlay-settings",
        json={"font_size": 40, "speed": 120, "opacity": 0.85, "font": "Microsoft YaHei"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["font_size"] == 40
    assert response.json()["opacity"] == 0.85

    # 公开端点反映新值（大屏客户端通过此接口获取）
    public = await client.get("/api/v1/public/activities/MEET2026")
    body = public.json()
    assert body["overlay_font_size"] == 40
    assert body["overlay_speed"] == 120
    assert body["overlay_opacity"] == 0.85
    assert body["overlay_font"] == "Microsoft YaHei"


async def test_overlay_settings_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.put(
        f"/api/v1/activities/{activity.id}/overlay-settings",
        json={"font_size": 40, "speed": 120, "opacity": 0.85, "font": "Segoe UI"},
    )
    assert response.status_code == 401


async def test_overlay_settings_invalid_values_rejected(client: AsyncClient, activity, admin_token: str) -> None:
    response = await client.put(
        f"/api/v1/activities/{activity.id}/overlay-settings",
        json={"font_size": 400, "speed": 120, "opacity": 2.0, "font": "Segoe UI"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_create_activity(client: AsyncClient, admin_token: str) -> None:
    response = await client.post(
        "/api/v1/activities",
        json={"name": "发布会", "public_code": "launch2026"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["public_code"] == "LAUNCH2026"  # 自动转大写
    assert body["name"] == "发布会"

    # 出现在列表中
    listing = await client.get("/api/v1/activities", headers={"Authorization": f"Bearer {admin_token}"})
    assert listing.status_code == 200
    assert any(a["public_code"] == "LAUNCH2026" for a in listing.json())

    # 参与者可通过活动码访问
    public = await client.get("/api/v1/public/activities/launch2026")
    assert public.status_code == 200
    assert public.json()["name"] == "发布会"


async def test_create_activity_requires_admin(client: AsyncClient) -> None:
    response = await client.post("/api/v1/activities", json={"name": "发布会", "public_code": "EVENT01"})
    assert response.status_code == 401


async def test_create_activity_duplicate_code(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    first = await client.post("/api/v1/activities", json={"name": "活动A", "public_code": "DUP001"}, headers=headers)
    assert first.status_code == 201
    second = await client.post("/api/v1/activities", json={"name": "活动B", "public_code": "dup001"}, headers=headers)
    assert second.status_code == 409


async def test_create_activity_invalid_code_rejected(client: AsyncClient, admin_token: str) -> None:
    response = await client.post(
        "/api/v1/activities",
        json={"name": "非法码", "public_code": "ab c"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_list_activities_requires_admin(client: AsyncClient) -> None:
    response = await client.get("/api/v1/activities")
    assert response.status_code == 401


async def test_update_activity_name_and_status(client: AsyncClient, activity, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}

    renamed = await client.put(
        f"/api/v1/activities/{activity.id}",
        json={"name": "改名后的活动", "status": "closed"},
        headers=headers,
    )
    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "改名后的活动"
    assert body["status"] == "closed"

    # 公开端点反映更新
    public = await client.get("/api/v1/public/activities/MEET2026")
    assert public.json()["name"] == "改名后的活动"
    assert public.json()["status"] == "closed"


async def test_update_activity_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.put(f"/api/v1/activities/{activity.id}", json={"name": "无权改名"})
    assert response.status_code == 401


async def test_update_activity_empty_name_rejected(client: AsyncClient, activity, admin_token: str) -> None:
    response = await client.put(
        f"/api/v1/activities/{activity.id}",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_delete_activity(client: AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = (await client.post("/api/v1/activities", json={"name": "待删除", "public_code": "DEL001"}, headers=headers)).json()

    deleted = await client.delete(f"/api/v1/activities/{created['id']}", headers=headers)
    assert deleted.status_code == 204

    # 参与者侧 404，列表中不再出现
    public = await client.get("/api/v1/public/activities/DEL001")
    assert public.status_code == 404
    listing = await client.get("/api/v1/activities", headers=headers)
    assert all(a["id"] != created["id"] for a in listing.json())


async def test_delete_activity_cascades(client: AsyncClient, activity, admin_token: str) -> None:
    # 加入参与者、提交并批准一条弹幕，再删除活动
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "级联"})).json()
    danmaku = (
        await client.post(
            "/api/v1/public/danmaku",
            json={"activity_id": joined["activity_id"], "content": "删除前提交"},
            headers={"Authorization": f"Bearer {joined['session_token']}"},
        )
    ).json()
    await client.post(
        f"/api/v1/danmaku/{danmaku['id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    deleted = await client.delete(
        f"/api/v1/activities/{activity.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deleted.status_code == 204

    # 级联后：审核队列与统计均不再残留该活动的数据
    queue = await client.get(
        f"/api/v1/activities/{activity.id}/moderation-queue",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert queue.status_code == 200
    assert queue.json() == []
    stats = await client.get(f"/api/v1/activities/{activity.id}/stats")
    assert stats.json()["published_count"] == 0


async def test_delete_activity_requires_admin(client: AsyncClient, activity) -> None:
    response = await client.delete(f"/api/v1/activities/{activity.id}")
    assert response.status_code == 401


async def test_delete_unknown_activity_404(client: AsyncClient, admin_token: str) -> None:
    response = await client.delete(
        "/api/v1/activities/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def _set_status(client: AsyncClient, activity_id: str, status: str, admin_token: str) -> None:
    response = await client.put(
        f"/api/v1/activities/{activity_id}",
        json={"status": status},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


async def test_join_blocked_for_draft_activity(client: AsyncClient, activity, admin_token: str) -> None:
    await _set_status(client, str(activity.id), "draft", admin_token)
    response = await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "太早"})
    assert response.status_code == 409
    assert response.json()["detail"] == "活动尚未开始"


async def test_join_blocked_for_closed_activity(client: AsyncClient, activity, admin_token: str) -> None:
    await _set_status(client, str(activity.id), "closed", admin_token)
    response = await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "太晚"})
    assert response.status_code == 409
    assert response.json()["detail"] == "活动已结束"


async def test_submit_blocked_after_activity_closed(client: AsyncClient, activity, admin_token: str) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "先加入"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    body = {"activity_id": joined["activity_id"], "content": "活动结束后发送"}

    await _set_status(client, str(activity.id), "closed", admin_token)
    response = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "活动已结束"

    # 重新开放后可正常投稿
    await _set_status(client, str(activity.id), "live", admin_token)
    response = await client.post("/api/v1/public/danmaku", json=body, headers=headers)
    assert response.status_code == 201

async def test_multiline_danmaku_rejected_by_default(client: AsyncClient, activity) -> None:
    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "多行侠"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    response = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "第一行\n第二行"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "多行" in response.json()["detail"]


async def test_multiline_allowed_when_enabled(client: AsyncClient, activity, admin_token: str) -> None:
    enabled = await client.put(
        f"/api/v1/activities/{activity.id}",
        json={"allow_multiline": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["allow_multiline"] is True

    joined = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "多行开"})).json()
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    response = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined["activity_id"], "content": "第一行\n第二行"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["content"] == "第一行\n第二行"


async def test_multiline_default_false_for_new_activity(client: AsyncClient, admin_token: str) -> None:
    created = await client.post(
        "/api/v1/activities",
        json={"name": "多行测试", "public_code": "MULTI1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 201
    public = await client.get("/api/v1/public/activities/MULTI1")
    assert public.status_code == 200
    assert public.json()["allow_multiline"] is False



async def test_cross_activity_token_rejected(client: AsyncClient, admin_token: str, activity) -> None:
    """参与者令牌绑定到加入时的活动，跨活动投稿必须被拒绝。"""
    # 创建第二个活动
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.post("/api/v1/activities", json={"name": "另一活动", "public_code": "OTHER1"}, headers=headers)

    # 在活动 A (MEET2026) 中加入
    joined_a = (await client.post("/api/v1/public/activities/MEET2026/join", json={"nickname": "跨活动者"})).json()
    assert str(joined_a["activity_id"]) == str(activity.id)

    # 用活动 A 的令牌向活动 B (OTHER1) 投稿 -> 403
    other_activity = (await client.get("/api/v1/public/activities/OTHER1")).json()
    response = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": other_activity["id"], "content": "跨活动弹幕"},
        headers={"Authorization": f"Bearer {joined_a['session_token']}"},
    )
    assert response.status_code == 403
    assert "不匹配" in response.json()["detail"]

    # 用同一令牌向活动 A 投稿 -> 正常 201
    response_ok = await client.post(
        "/api/v1/public/danmaku",
        json={"activity_id": joined_a["activity_id"], "content": "正常弹幕"},
        headers={"Authorization": f"Bearer {joined_a['session_token']}"},
    )
    assert response_ok.status_code == 201
