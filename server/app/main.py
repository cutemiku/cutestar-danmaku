import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import store
from .auth import get_admin, get_participant
from .bus import bus
from .config import settings
from .database import get_session, run_migrations, session_factory
from .db_models import ActivityRow, BanRow, DanmakuRow, EventRow, ParticipantRow, ScreenKeyRow
from .models import (
    ActivityCreate,
    ActivityUpdate,
    AdminLogin,
    Ban,
    BanCreate,
    BanTargetType,
    ControlRequest,
    Danmaku,
    DanmakuCreate,
    DanmakuLogItem,
    DanmakuSettings,
    DanmakuStatus,
    JoinRequest,
    JoinResponse,
    OverlaySettings,
    ScreenKey,
    ScreenKeyCreate,
    ScreenRequestStatus,
)
from .moderation import ModerationVerdict, check_content, warmup
from .ratelimit import (
    admin_login_limiter,
    client_ip,
    danmaku_limiter,
    join_limiter,
    ws_limiter,
)
from .security import create_admin_token, decode_admin_token, generate_screen_key, verify_password
from .seed import seed_admin

logger = logging.getLogger("cutestar")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_migrations()
    await seed_admin()
    # 后台预热阿里云内容安全 SDK，避免首条弹幕触发秒级冷启动（不阻塞启动）
    try:
        asyncio.create_task(warmup())
    except RuntimeError:
        pass
    yield
    await bus.aclose()


app = FastAPI(title="Cutestar Danmaku API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_activity_open(activity: ActivityRow) -> None:
    """状态闸门：未开始或已结束的活动不接受加入/投稿。"""
    if activity.status == "draft":
        raise HTTPException(status_code=409, detail="活动尚未开始")
    if activity.status == "closed":
        raise HTTPException(status_code=409, detail="活动已结束")


def _activity_json(activity: ActivityRow) -> dict[str, object]:
    return {
        "id": str(activity.id),
        "public_code": activity.public_code,
        "name": activity.name,
        "status": activity.status,
        "submission_paused": activity.submission_paused,
        "slow_mode_seconds": activity.slow_mode_seconds,
        "danmaku_color_mode": activity.danmaku_color_mode,
        "danmaku_default_color": activity.danmaku_default_color,
        "allow_custom_color": activity.allow_custom_color,
        "auto_moderation_enabled": activity.auto_moderation_enabled,
        "auto_moderation_configured": bool(
            settings.alibaba_access_key_id and settings.alibaba_access_key_secret
        ),
        "allow_multiline": activity.allow_multiline,
        "overlay_font_size": activity.overlay_font_size,
        "overlay_speed": activity.overlay_speed,
        "overlay_opacity": activity.overlay_opacity,
        "overlay_font": activity.overlay_font,
    }


def _danmaku_json(danmaku: DanmakuRow) -> dict[str, object]:
    return {
        "id": str(danmaku.id),
        "activity_id": str(danmaku.activity_id),
        "participant_id": str(danmaku.participant_id),
        "content": danmaku.content,
        "color": danmaku.color,
        "status": danmaku.status,
        "submitted_at": danmaku.submitted_at.isoformat(),
    }


def _client_ip(request: Request) -> str | None:
    """优先取 X-Forwarded-For 第一个地址（反代场景），否则直连地址。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


async def _publish(activity_id: UUID, event: EventRow) -> None:
    try:
        await bus.publish(str(activity_id), store.event_envelope(event))
    except Exception:
        logger.warning("事件广播失败，将由 WS 端按序号从 DB 回放补偿", exc_info=True)


_online: dict[str, int] = defaultdict(int)

# ── 活跃参与者统计 ──
# 发送端不建立 WS 连接，因此"在线人数"按活跃参与者计：
# 加入活动、发送弹幕、轮询 stats（携带参与者 token 视为心跳）都会刷新活跃时间。
# 内存存储即可满足单 worker 现状（Redis 留空），重启后清空可接受。
ACTIVE_WINDOW_SECONDS = 300  # 5 分钟内活跃视为在线

_active_participants: dict[str, dict[str, float]] = defaultdict(dict)


def _touch_active(activity_id: str, participant_id: UUID) -> None:
    _active_participants[activity_id][str(participant_id)] = time.monotonic()


def _active_count(activity_id: str) -> int:
    now = time.monotonic()
    alive = {pid: ts for pid, ts in _active_participants.get(activity_id, {}).items()
             if now - ts <= ACTIVE_WINDOW_SECONDS}
    _active_participants[activity_id] = alive  # 顺带清理过期项
    return len(alive)


@app.get("/api/v1/activities/{activity_id}/stats")
async def activity_stats(
    activity_id: UUID,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    # 发送端轮询 stats 时携带参与者令牌，作为心跳保持"在线"状态
    if authorization and authorization.startswith("Bearer "):
        participant = await store.participant_by_token(session, authorization[7:])
        if participant is not None and str(participant.activity_id) == str(activity_id):
            _touch_active(activity_id, participant.id)
    published = await store.published_count(session, activity_id)
    return {"online_count": _active_count(str(activity_id)), "published_count": published}


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("select 1"))
    return {"status": "ok", "service": "cutestar-danmaku", "database": "ok"}


@app.post(f"/api/v1/auth/admin/login/{settings.admin_entry_path}", include_in_schema=False)
async def admin_login(
    http_request: Request,
    request: AdminLogin,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    # 登录限速：单 IP 5 分钟 20 次，防暴力破解
    admin_login_limiter.check(client_ip(http_request))
    admin = await store.admin_by_username(session, request.username)
    if admin is None or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": create_admin_token(admin.username), "token_type": "bearer"}


@app.get(f"/api/v1/auth/admin/entry/{settings.admin_entry_path}", status_code=204, include_in_schema=False)
async def admin_entry_probe() -> None:
    """Only the configured opaque entry exists; other paths naturally return 404."""
    return None


@app.get("/api/v1/public/activities/{code}")
async def public_activity(code: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    activity = await store.activity_by_code(session, code)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    return _activity_json(activity)


@app.post("/api/v1/public/activities/{code}/join", response_model=JoinResponse)
async def join_activity(
    http_request: Request,
    code: str,
    request: JoinRequest,
    session: AsyncSession = Depends(get_session),
) -> JoinResponse:
    # 加入限速：单 IP 10 秒 3 次，防批量注册参与者
    join_limiter.check(client_ip(http_request))
    activity = await store.activity_by_code(session, code)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    _check_activity_open(activity)
    participant = await store.join_participant(session, activity.id, request.nickname)
    _touch_active(str(activity.id), participant.id)
    return JoinResponse(
        participant_id=participant.id,
        activity_id=activity.id,
        nickname=participant.nickname,
        session_token=participant.token,
    )


@app.post("/api/v1/public/danmaku", response_model=Danmaku, status_code=201)
async def create_danmaku(
    request: Request,
    body: DanmakuCreate,
    participant: ParticipantRow = Depends(get_participant),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
) -> Danmaku:
    # 活动-参与者一致性：防止参与者令牌被跨活动使用
    if str(participant.activity_id) != str(body.activity_id):
        raise HTTPException(status_code=403, detail="参与者令牌与目标活动不匹配")
    activity = await store.activity_by_id(session, body.activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动会话不存在")
    _check_activity_open(activity)
    if activity.submission_paused:
        raise HTTPException(status_code=409, detail="活动暂时停止投稿")
    # 发弹幕限速：单参与者 10 秒 5 条（配合活动级 slow_mode，防刷屏）
    danmaku_limiter.check(f"p:{participant.id}")
    danmaku_limiter.check(f"ip:{_client_ip(request)}")
    # 多行弹幕二次核验：服务端权威判定，防止绕过前端在禁止多行时注入换行刷屏
    if not activity.allow_multiline and "\n" in body.content:
        raise HTTPException(status_code=422, detail="当前活动不允许发送多行弹幕")

    ip_address = _client_ip(request)
    ban = await store.active_ban(
        session,
        activity.id,
        participant_id=participant.id,
        ip_address=ip_address,
        device_fingerprint=body.device_fingerprint,
    )
    if ban is not None:
        if ban.expires_at is None:
            detail = "你已被禁言，无法发送弹幕"
        else:
            # SQLite 读出的时间为 naive，补 UTC 时区后再计算剩余时间
            expires = ban.expires_at.replace(tzinfo=timezone.utc)
            remaining = expires - datetime.now(timezone.utc)
            minutes = max(1, int(remaining.total_seconds() // 60))
            detail = f"你已被禁言，剩余 {minutes} 分钟"
        raise HTTPException(status_code=403, detail=detail)

    if participant.activity_id != activity.id:
        raise HTTPException(status_code=403, detail="参与者令牌与活动不匹配")

    if idempotency_key:
        existing = await store.danmaku_by_idempotency(session, activity.id, idempotency_key)
        if existing is not None:
            return _danmaku_json(existing)
    danmaku = await store.create_danmaku(
        session,
        activity_id=activity.id,
        participant_id=participant.id,
        content=body.content,
        color=store.resolve_danmaku_color(activity, body.color),
        idempotency_key=idempotency_key,
        ip_address=ip_address,
        device_fingerprint=body.device_fingerprint,
    )
    _touch_active(str(activity.id), participant.id)

    # 自动审核：如果活动开启了自动审核，调用阿里云内容安全 API
    auto_moderated = False
    if activity.auto_moderation_enabled:
        result = await check_content(body.content)
        if result.verdict == ModerationVerdict.PASSED:
            danmaku.status = DanmakuStatus.PUBLISHED.value
            auto_moderated = True
            logger.info("自动审核通过: %s (labels=%s)", danmaku.id, result.labels)
        elif result.verdict == ModerationVerdict.REJECTED:
            danmaku.status = DanmakuStatus.REJECTED.value
            auto_moderated = True
            logger.info("自动审核拒绝: %s (labels=%s, risk=%s, words=%s)",
                        danmaku.id, result.labels, result.risk_level, result.risk_words)
        else:
            logger.info("自动审核待复核: %s (labels=%s, risk=%s)", danmaku.id, result.labels, result.risk_level)

    event_type = "danmaku.pending_created"
    if auto_moderated:
        event_type = "danmaku.published" if danmaku.status == DanmakuStatus.PUBLISHED.value else "danmaku.rejected"

    event = await store.add_event(session, activity.id, event_type, _danmaku_json(danmaku))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await store.danmaku_by_idempotency(session, activity.id, idempotency_key)
        if existing is not None:
            return _danmaku_json(existing)
        raise
    await _publish(activity.id, event)
    return _danmaku_json(danmaku)


@app.get("/api/v1/activities")
async def list_activities(
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    return [_activity_json(a) for a in await store.list_activities(session)]


@app.post("/api/v1/activities", status_code=201)
async def create_activity(
    request: ActivityCreate,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        activity = await store.create_activity(
            session, name=request.name.strip(), public_code=request.public_code.upper()
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="活动码已存在")
    return _activity_json(activity)


@app.put("/api/v1/activities/{activity_id}")
async def update_activity(
    activity_id: UUID,
    request: ActivityUpdate,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    activity = await store.activity_by_id(session, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    previous_status = activity.status
    await store.update_activity(
        session,
        activity,
        name=request.name,
        status=request.status,
        auto_moderation_enabled=request.auto_moderation_enabled,
        allow_multiline=request.allow_multiline,
    )
    event = None
    if request.status is not None and request.status.value != previous_status:
        event = await store.add_event(
            session, activity.id, "activity.status_changed",
            {"status": activity.status, "previous_status": previous_status},
        )
    await session.commit()
    if event is not None:
        await _publish(activity.id, event)
    return _activity_json(activity)


@app.delete("/api/v1/activities/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    activity = await store.activity_by_id(session, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    await store.delete_activity(session, activity_id)


@app.get("/api/v1/activities/{activity_id}/moderation-queue", response_model=list[Danmaku])
async def moderation_queue(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> list[Danmaku]:
    return [_danmaku_json(d) for d in await store.moderation_queue(session, activity_id)]


@app.get("/api/v1/activities/{activity_id}/danmaku-logs")
async def danmaku_logs(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> dict[str, object]:
    rows = await store.danmaku_logs(session, activity_id, limit=min(limit, 200), offset=offset, status=status)
    items = [
        DanmakuLogItem(
            id=row.id,
            activity_id=row.activity_id,
            participant_id=row.participant_id,
            nickname=nickname,
            content=row.content,
            color=row.color,
            status=DanmakuStatus(row.status),
            ip_address=row.ip_address,
            device_fingerprint=row.device_fingerprint,
            submitted_at=row.submitted_at,
        ).model_dump(mode="json")
        for row, nickname in rows
    ]
    return {"items": items, "total": await store.danmaku_logs_count(session, activity_id, status)}


@app.post("/api/v1/activities/{activity_id}/bans", response_model=Ban, status_code=201)
async def create_ban(
    activity_id: UUID,
    request: BanCreate,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> Ban:
    if await store.activity_by_id(session, activity_id) is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    # 禁言目标值统一按字符串存储，参与者 ID 转字符串避免格式歧义
    target_value = str(request.target_value)
    if request.target_type == BanTargetType.PARTICIPANT:
        try:
            participant_id = UUID(target_value)
        except ValueError:
            raise HTTPException(status_code=422, detail="参与者 ID 无效")
        if await session.get(ParticipantRow, participant_id) is None:
            raise HTTPException(status_code=404, detail="参与者不存在")
    ban = await store.create_ban(
        session,
        activity_id=activity_id,
        target_type=request.target_type.value,
        target_value=target_value,
        reason=request.reason,
        duration_minutes=request.duration_minutes,
        banned_by=_admin,
    )
    await session.commit()
    await session.refresh(ban)
    return Ban(
        id=ban.id,
        activity_id=ban.activity_id,
        target_type=request.target_type,
        target_value=ban.target_value,
        reason=ban.reason,
        banned_by=ban.banned_by,
        expires_at=ban.expires_at,
        created_at=ban.created_at,
    )


@app.get("/api/v1/activities/{activity_id}/bans", response_model=list[Ban])
async def list_bans(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> list[Ban]:
    bans = await store.list_bans(session, activity_id)
    return [
        Ban(
            id=ban.id,
            activity_id=ban.activity_id,
            target_type=BanTargetType(ban.target_type),
            target_value=ban.target_value,
            reason=ban.reason,
            banned_by=ban.banned_by,
            expires_at=ban.expires_at,
            created_at=ban.created_at,
        )
        for ban in bans
    ]


@app.delete("/api/v1/activities/{activity_id}/bans/{ban_id}", status_code=204)
async def delete_ban(
    activity_id: UUID,
    ban_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    ban = await session.get(BanRow, ban_id)
    if ban is None or ban.activity_id != activity_id:
        raise HTTPException(status_code=404, detail="禁言记录不存在")
    await store.delete_ban(session, ban_id)
    await session.commit()


@app.get("/api/v1/public/screen-keys/status", response_model=ScreenRequestStatus)
async def screen_request_status(
    device_id: str,
    session: AsyncSession = Depends(get_session),
) -> ScreenRequestStatus:
    """大屏查询自身授权状态（公开，凭 device_id）：pending 等待审批，approved 返回明文 sk。"""
    status, key = await store.screen_request_status(session, device_id)
    return ScreenRequestStatus(status=status, key=key)


@app.get("/api/v1/activities/{activity_id}/screen-keys/pending", response_model=list[ScreenKey])
async def list_pending_screen_requests(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ScreenKey]:
    """待审批的大屏接入请求列表（管理员）。"""
    rows = await store.list_pending_screen_requests(session, activity_id)
    return [
        ScreenKey(
            id=row.id,
            activity_id=row.activity_id,
            label=row.label,
            device_id=row.device_id,
            enabled=row.enabled,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.post("/api/v1/activities/{activity_id}/screen-keys/approve/{device_id}", response_model=ScreenKey)
async def approve_screen_request(
    activity_id: UUID,
    device_id: str,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> ScreenKey:
    """批准大屏接入请求：生成 sk 并授权，大屏轮询到 approved 后自动下发。"""
    row = await session.scalar(select(ScreenKeyRow).where(ScreenKeyRow.device_id == device_id))
    if row is None or row.activity_id != activity_id:
        raise HTTPException(status_code=404, detail="大屏请求不存在")
    row, key = await store.approve_screen_request(session, device_id)
    await session.commit()
    await session.refresh(row)
    return ScreenKey(
        id=row.id,
        activity_id=row.activity_id,
        label=row.label,
        device_id=row.device_id,
        enabled=row.enabled,
        created_at=row.created_at,
        key=key,
    )


@app.post("/api/v1/activities/{activity_id}/screen-keys", response_model=ScreenKey, status_code=201)
async def create_screen_key(
    activity_id: UUID,
    request: ScreenKeyCreate,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> ScreenKey:
    if await store.activity_by_id(session, activity_id) is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    key = generate_screen_key()
    row = await store.create_screen_key(session, activity_id=activity_id, key=key, label=request.label.strip())
    await session.commit()
    await session.refresh(row)
    return ScreenKey(
        id=row.id,
        activity_id=row.activity_id,
        label=row.label,
        enabled=row.enabled,
        created_at=row.created_at,
        key=key,
    )


@app.get("/api/v1/activities/{activity_id}/screen-keys", response_model=list[ScreenKey])
async def list_screen_keys(
    activity_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ScreenKey]:
    rows = await store.list_screen_keys(session, activity_id)
    return [
        ScreenKey(
            id=row.id,
            activity_id=row.activity_id,
            label=row.label,
            enabled=row.enabled,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.delete("/api/v1/activities/{activity_id}/screen-keys/{key_id}", status_code=204)
async def delete_screen_key(
    activity_id: UUID,
    key_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await store.delete_screen_key(session, activity_id, key_id):
        raise HTTPException(status_code=404, detail="密钥不存在")
    await session.commit()


@app.post("/api/v1/danmaku/{danmaku_id}/approve", response_model=Danmaku)
async def approve_danmaku(
    danmaku_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> Danmaku:
    danmaku = await store.danmaku_by_id(session, danmaku_id)
    if danmaku is None:
        raise HTTPException(status_code=404, detail="弹幕不存在")
    await store.set_danmaku_status(session, danmaku, DanmakuStatus.PUBLISHED)
    event = await store.add_event(session, danmaku.activity_id, "danmaku.published", _danmaku_json(danmaku))
    await session.commit()
    await _publish(danmaku.activity_id, event)
    return _danmaku_json(danmaku)


@app.post("/api/v1/danmaku/{danmaku_id}/reject", response_model=Danmaku)
async def reject_danmaku(
    danmaku_id: UUID,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> Danmaku:
    danmaku = await store.danmaku_by_id(session, danmaku_id)
    if danmaku is None:
        raise HTTPException(status_code=404, detail="弹幕不存在")
    await store.set_danmaku_status(session, danmaku, DanmakuStatus.REJECTED)
    event = await store.add_event(session, danmaku.activity_id, "danmaku.rejected", _danmaku_json(danmaku))
    await session.commit()
    await _publish(danmaku.activity_id, event)
    return _danmaku_json(danmaku)


@app.post("/api/v1/activities/{activity_id}/controls")
async def control_activity(
    activity_id: UUID,
    request: ControlRequest,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    activity = await store.activity_by_id(session, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    if request.action == "pause_submissions":
        await store.set_submission_paused(session, activity, True)
    elif request.action == "resume_submissions":
        await store.set_submission_paused(session, activity, False)
    elif request.action == "slow_mode":
        await store.set_slow_mode(session, activity, request.seconds)
    event = await store.add_event(session, activity.id, "activity.control_changed", request.model_dump())
    if request.action == "clear_screen":
        event = await store.add_event(session, activity.id, "screen.clear_requested", {})
    await session.commit()
    await _publish(activity.id, event)
    return store.event_envelope(event)


@app.put("/api/v1/activities/{activity_id}/danmaku-settings")
async def update_danmaku_settings(
    activity_id: UUID,
    settings: DanmakuSettings,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    activity = await store.activity_by_id(session, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    await store.set_danmaku_settings(session, activity, settings)
    event = await store.add_event(session, activity.id, "activity.danmaku_settings_changed", settings.model_dump())
    await session.commit()
    await _publish(activity.id, event)
    return {
        "color_mode": activity.danmaku_color_mode,
        "default_color": activity.danmaku_default_color,
        "allow_custom_color": activity.allow_custom_color,
    }


@app.put("/api/v1/activities/{activity_id}/overlay-settings")
async def update_overlay_settings(
    activity_id: UUID,
    settings: OverlaySettings,
    _admin: str = Depends(get_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    activity = await store.activity_by_id(session, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    await store.set_overlay_settings(session, activity, settings)
    event = await store.add_event(session, activity.id, "activity.overlay_settings_changed", settings.model_dump())
    await session.commit()
    await _publish(activity.id, event)
    return {
        "font_size": activity.overlay_font_size,
        "speed": activity.overlay_speed,
        "opacity": activity.overlay_opacity,
        "font": activity.overlay_font,
    }


@app.websocket("/api/v1/activities/{activity_id}/events")
async def activity_events(websocket: WebSocket, activity_id: UUID) -> None:
    # WS 连接限速：单 IP 5 分钟最多 8 个并发连接，防连接耗尽
    try:
        ws_limiter.check(client_ip(websocket))
    except HTTPException:
        await websocket.close(code=1013, reason="连接过于频繁")
        return
    await websocket.accept()
    key = str(activity_id)
    # 大屏授权：携带有效 sk 直接连接；管理端可携带 admin token 免 sk
    screen_key = websocket.query_params.get("sk", "")
    admin_token = websocket.query_params.get("admin_token", "")
    device_id = websocket.query_params.get("device_id", "")
    async with session_factory() as session:
        if await store.activity_by_id(session, activity_id) is None:
            await websocket.close(code=1008, reason="活动不存在")
            return
        is_admin = bool(admin_token) and decode_admin_token(admin_token) is not None
        if not is_admin and not await store.screen_key_valid(session, activity_id, screen_key):
            if device_id and len(device_id) <= 64:
                # 首次连接自动注册待审批请求；已注册则保持 pending 状态
                await store.screen_request_for_device(
                    session, activity_id=activity_id, device_id=device_id, label=device_id[:16]
                )
                await session.commit()
                await websocket.close(code=1008, reason="等待管理员审批")
            else:
                await websocket.close(code=1008, reason="密钥无效或未授权")
            return
    _online[key] += 1
    # 从查询参数读取客户端上次确认的序列号，跳过已处理的事件
    try:
        cursor = int(websocket.query_params.get("last_sequence", "0"))
    except (ValueError, TypeError):
        cursor = 0

    async def replay(*, replay: bool) -> None:
        nonlocal cursor
        async with session_factory() as session:
            for row in await store.events_after(session, activity_id, cursor):
                envelope = store.event_envelope(row)
                if replay:
                    # 断线补偿事件：客户端据此错峰展示，避免一股脑刷屏
                    envelope["replay"] = True
                try:
                    await websocket.send_json(envelope)
                except (WebSocketDisconnect, RuntimeError):
                    # 客户端已断开：uvicorn 会抛 RuntimeError（send after close），按断开处理
                    raise WebSocketDisconnect()
                cursor = row.id

    async def consume_client() -> None:
        nonlocal cursor
        while True:
            try:
                message = await websocket.receive_json()
            except (WebSocketDisconnect, ValueError):
                raise WebSocketDisconnect()
            cursor = max(cursor, int(message.get("last_sequence", cursor)))

    async def pump() -> None:
        # 连接时先回放历史事件（断线补偿，标记 replay），随后随总线消息增量回放（实时）
        await replay(replay=True)
        async for _ in subscription:
            await replay(replay=False)

    client_task = asyncio.create_task(consume_client())
    subscription = bus.subscribe(key)
    pump_task = asyncio.create_task(pump())
    try:
        # 任一任务结束（客户端断开 / 发送失败）即退出，及时清理连接
        done, _ = await asyncio.wait({client_task, pump_task}, return_when=asyncio.FIRST_COMPLETED)
        exit_exc: BaseException | None = None
        for task in done:
            try:
                task.result()
            except WebSocketDisconnect:
                pass
            except BaseException as exc:
                if exit_exc is None:
                    exit_exc = exc
        if exit_exc is not None:
            raise exit_exc
    except WebSocketDisconnect:
        pass
    finally:
        _online[key] = max(0, _online[key] - 1)
        pump_task.cancel()
        client_task.cancel()
        # 先等两个任务完全退出（消耗 CancelledError/WebSocketDisconnect），
        # 再关闭订阅生成器，避免在生成器仍在运行时报 aclose(): already running
        for task in (pump_task, client_task):
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                pass
        try:
            await subscription.aclose()
        except RuntimeError:
            pass  # pump 退出时已关闭生成器
