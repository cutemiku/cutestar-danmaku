import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db_models import (
    ActivityRow,
    AdminRow,
    BanRow,
    DanmakuRow,
    EventRow,
    ParticipantRow,
    ScreenKeyRow,
)
from .models import ActivityStatus, DanmakuSettings, DanmakuStatus, OverlaySettings
from .security import generate_participant_token, generate_screen_key

# 随机模式下使用的调色板：浅色系，保证在深色大屏上可读
RANDOM_PALETTE = [
    "#FFFFFF",
    "#FFD54F",
    "#81C784",
    "#64B5F6",
    "#F48FB1",
    "#CE93D8",
    "#FF8A65",
    "#4DD0E1",
]


def resolve_danmaku_color(activity: ActivityRow, requested: str | None) -> str:
    """服务端权威决定弹幕颜色：未开启自定义时忽略用户提交的颜色。"""
    if requested is not None and activity.allow_custom_color:
        return requested.upper()
    if activity.danmaku_color_mode == "random":
        return random.choice(RANDOM_PALETTE)
    return activity.danmaku_default_color.upper()


async def activity_by_code(session: AsyncSession, code: str) -> ActivityRow | None:
    return await session.scalar(select(ActivityRow).where(ActivityRow.public_code == code.upper()))


async def activity_by_id(session: AsyncSession, activity_id: UUID) -> ActivityRow | None:
    return await session.get(ActivityRow, activity_id)


async def create_activity(session: AsyncSession, *, name: str, public_code: str) -> ActivityRow:
    activity = ActivityRow(name=name, public_code=public_code)
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    return activity


async def list_activities(session: AsyncSession) -> list[ActivityRow]:
    result = await session.scalars(select(ActivityRow).order_by(ActivityRow.created_at))
    return list(result)


async def update_activity(
    session: AsyncSession,
    activity: ActivityRow,
    *,
    name: str | None = None,
    status: ActivityStatus | None = None,
    auto_moderation_enabled: bool | None = None,
    allow_multiline: bool | None = None,
) -> None:
    if name is not None:
        activity.name = name
    if status is not None:
        activity.status = status.value
    if auto_moderation_enabled is not None:
        activity.auto_moderation_enabled = auto_moderation_enabled
    if allow_multiline is not None:
        activity.allow_multiline = allow_multiline
    await session.flush()


async def delete_activity(session: AsyncSession, activity_id: UUID) -> None:
    """级联删除活动及其事件、弹幕、参与者（依赖关系先删子表）。"""
    await session.execute(delete(EventRow).where(EventRow.activity_id == activity_id))
    await session.execute(delete(DanmakuRow).where(DanmakuRow.activity_id == activity_id))
    await session.execute(delete(ParticipantRow).where(ParticipantRow.activity_id == activity_id))
    await session.execute(delete(ActivityRow).where(ActivityRow.id == activity_id))
    await session.commit()


async def join_participant(session: AsyncSession, activity_id: UUID, nickname: str) -> ParticipantRow:
    participant = ParticipantRow(activity_id=activity_id, nickname=nickname, token=generate_participant_token())
    session.add(participant)
    await session.commit()
    await session.refresh(participant)
    return participant


async def participant_by_token(session: AsyncSession, token: str) -> ParticipantRow | None:
    return await session.scalar(select(ParticipantRow).where(ParticipantRow.token == token))


async def admin_by_username(session: AsyncSession, username: str) -> AdminRow | None:
    return await session.scalar(select(AdminRow).where(AdminRow.username == username))


async def danmaku_by_idempotency(session: AsyncSession, activity_id: UUID, key: str) -> DanmakuRow | None:
    return await session.scalar(
        select(DanmakuRow).where(DanmakuRow.activity_id == activity_id, DanmakuRow.idempotency_key == key)
    )


async def danmaku_by_id(session: AsyncSession, danmaku_id: UUID) -> DanmakuRow | None:
    return await session.get(DanmakuRow, danmaku_id)


async def create_danmaku(
    session: AsyncSession,
    *,
    activity_id: UUID,
    participant_id: UUID,
    content: str,
    color: str,
    idempotency_key: str | None = None,
    ip_address: str | None = None,
    device_fingerprint: str | None = None,
) -> DanmakuRow:
    danmaku = DanmakuRow(
        activity_id=activity_id,
        participant_id=participant_id,
        content=content,
        color=color,
        idempotency_key=idempotency_key,
        ip_address=ip_address,
        device_fingerprint=device_fingerprint,
    )
    session.add(danmaku)
    await session.flush()
    return danmaku


async def moderation_queue(session: AsyncSession, activity_id: UUID) -> list[DanmakuRow]:
    result = await session.scalars(
        select(DanmakuRow)
        .where(DanmakuRow.activity_id == activity_id, DanmakuRow.status == DanmakuStatus.PENDING.value)
        .order_by(DanmakuRow.submitted_at)
    )
    return list(result)


async def set_danmaku_status(session: AsyncSession, danmaku: DanmakuRow, status: DanmakuStatus) -> None:
    danmaku.status = status.value
    await session.flush()


async def set_submission_paused(session: AsyncSession, activity: ActivityRow, paused: bool) -> None:
    activity.submission_paused = paused
    await session.flush()


async def set_slow_mode(session: AsyncSession, activity: ActivityRow, seconds: int) -> None:
    activity.slow_mode_seconds = seconds
    await session.flush()


async def set_danmaku_settings(session: AsyncSession, activity: ActivityRow, settings: DanmakuSettings) -> None:
    activity.danmaku_color_mode = settings.color_mode.value
    activity.danmaku_default_color = settings.default_color.upper()
    activity.allow_custom_color = settings.allow_custom_color
    await session.flush()


async def set_overlay_settings(session: AsyncSession, activity: ActivityRow, settings: OverlaySettings) -> None:
    activity.overlay_font_size = settings.font_size
    activity.overlay_speed = settings.speed
    activity.overlay_opacity = settings.opacity
    activity.overlay_font = settings.font
    await session.flush()


async def add_event(session: AsyncSession, activity_id: UUID, event_type: str, payload: dict[str, object]) -> EventRow:
    event = EventRow(activity_id=activity_id, type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    return event


async def events_after(session: AsyncSession, activity_id: UUID, cursor: int, limit: int = 200) -> list[EventRow]:
    result = await session.scalars(
        select(EventRow)
        .where(EventRow.activity_id == activity_id, EventRow.id > cursor)
        .order_by(EventRow.id)
        .limit(limit)
    )
    return list(result)


def event_envelope(row: EventRow) -> dict[str, object]:
    return {
        "event_id": str(row.event_id),
        "sequence": row.id,
        "activity_id": str(row.activity_id),
        "type": row.type,
        "occurred_at": row.occurred_at.isoformat(),
        "payload": row.payload,
    }


async def published_count(session: AsyncSession, activity_id: UUID) -> int:
    return await session.scalar(
        select(func.count()).select_from(DanmakuRow).where(
            DanmakuRow.activity_id == activity_id, DanmakuRow.status == DanmakuStatus.PUBLISHED.value
        )
    ) or 0


async def danmaku_logs(
    session: AsyncSession,
    activity_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[tuple[DanmakuRow, str | None]]:
    """分页查询弹幕日志（含发送人昵称），按提交时间倒序。"""
    stmt = (
        select(DanmakuRow, ParticipantRow.nickname)
        .join(ParticipantRow, ParticipantRow.id == DanmakuRow.participant_id)
        .where(DanmakuRow.activity_id == activity_id)
        .order_by(DanmakuRow.submitted_at.desc(), DanmakuRow.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(DanmakuRow.status == status)
    result = await session.execute(stmt)
    return list(result)


async def danmaku_logs_count(session: AsyncSession, activity_id: UUID, status: str | None = None) -> int:
    stmt = select(func.count()).select_from(DanmakuRow).where(DanmakuRow.activity_id == activity_id)
    if status:
        stmt = stmt.where(DanmakuRow.status == status)
    return await session.scalar(stmt) or 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def active_ban(
    session: AsyncSession,
    activity_id: UUID,
    *,
    participant_id: UUID | None = None,
    ip_address: str | None = None,
    device_fingerprint: str | None = None,
) -> BanRow | None:
    """返回命中的有效禁言（按参与者/IP/设备指纹任一维度，未过期或永久）。"""
    now = _now()
    conditions = []
    if participant_id is not None:
        conditions.append(
            (BanRow.target_type == "participant") & (BanRow.target_value == str(participant_id))
        )
    if ip_address:
        conditions.append((BanRow.target_type == "ip") & (BanRow.target_value == ip_address))
    if device_fingerprint:
        conditions.append((BanRow.target_type == "fingerprint") & (BanRow.target_value == device_fingerprint))
    if not conditions:
        return None
    return await session.scalar(
        select(BanRow)
        .where(
            BanRow.activity_id == activity_id,
            or_(*conditions),
            or_(BanRow.expires_at.is_(None), BanRow.expires_at > now),
        )
        .order_by(BanRow.created_at.desc())
    )


async def create_ban(
    session: AsyncSession,
    *,
    activity_id: UUID,
    target_type: str,
    target_value: str,
    reason: str | None,
    duration_minutes: int | None,
    banned_by: str,
) -> BanRow:
    expires_at = _now() + timedelta(minutes=duration_minutes) if duration_minutes else None
    ban = BanRow(
        activity_id=activity_id,
        target_type=target_type,
        target_value=target_value,
        reason=reason,
        banned_by=banned_by,
        expires_at=expires_at,
    )
    session.add(ban)
    await session.flush()
    return ban


async def list_bans(session: AsyncSession, activity_id: UUID) -> list[BanRow]:
    result = await session.scalars(
        select(BanRow).where(BanRow.activity_id == activity_id).order_by(BanRow.created_at.desc())
    )
    return list(result)


async def delete_ban(session: AsyncSession, ban_id: UUID) -> bool:
    result = await session.execute(delete(BanRow).where(BanRow.id == ban_id))
    return result.rowcount > 0


# ── 大屏授权密钥（ScreenKey） ──


def hash_screen_key(key: str) -> str:
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


async def create_screen_key(
    session: AsyncSession,
    *,
    activity_id: UUID,
    key: str,
    label: str,
) -> ScreenKeyRow:
    row = ScreenKeyRow(activity_id=activity_id, key_hash=hash_screen_key(key), label=label)
    session.add(row)
    await session.flush()
    return row


async def screen_key_valid(session: AsyncSession, activity_id: UUID, key: str) -> bool:
    """校验大屏密钥：活动匹配、哈希一致且未被吊销。"""
    row = await session.scalar(
        select(ScreenKeyRow).where(
            ScreenKeyRow.activity_id == activity_id,
            ScreenKeyRow.key_hash == hash_screen_key(key),
            ScreenKeyRow.enabled.is_(True),
        )
    )
    return row is not None


async def list_screen_keys(session: AsyncSession, activity_id: UUID) -> list[ScreenKeyRow]:
    result = await session.scalars(
        select(ScreenKeyRow).where(ScreenKeyRow.activity_id == activity_id).order_by(ScreenKeyRow.created_at.desc())
    )
    return list(result)


async def delete_screen_key(session: AsyncSession, activity_id: UUID, key_id: UUID) -> bool:
    row = await session.get(ScreenKeyRow, key_id)
    if row is None or row.activity_id != activity_id:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def screen_request_for_device(
    session: AsyncSession,
    *,
    activity_id: UUID,
    device_id: str,
    label: str,
) -> ScreenKeyRow:
    """按 device_id 查大屏连接请求；不存在则注册一个新的（enabled=False 待审批）。"""
    row = await session.scalar(select(ScreenKeyRow).where(ScreenKeyRow.device_id == device_id))
    if row is None:
        row = ScreenKeyRow(activity_id=activity_id, device_id=device_id, label=label, enabled=False)
        session.add(row)
        await session.flush()
    return row


async def screen_request_status(
    session: AsyncSession,
    device_id: str,
) -> tuple[str, str | None]:
    """大屏查询自身授权状态：返回 (status, key)。

    status: pending=待审批 / approved=已批准 / rejected=已拒绝 / unknown=未注册
    key 仅在首次 approved 查询时返回明文（burn-after-reading），后续查询不再泄露。
    """
    row = await session.scalar(select(ScreenKeyRow).where(ScreenKeyRow.device_id == device_id))
    if row is None:
        return "unknown", None
    if row.enabled:
        key = row.key_plain or ""
        if row.key_plain:
            row.key_plain = None  # 一次性领取，清除明文
            await session.commit()
        return "approved", key
    return "pending", None


async def approve_screen_request(
    session: AsyncSession,
    device_id: str,
) -> tuple[ScreenKeyRow, str]:
    """管理员批准大屏请求：生成新 sk 并写入（enabled=True）。返回 (row, 明文 key)。"""
    row = await session.scalar(select(ScreenKeyRow).where(ScreenKeyRow.device_id == device_id))
    if row is None:
        raise ValueError("大屏请求不存在")
    key = generate_screen_key()
    row.key_hash = hash_screen_key(key)
    row.key_plain = key
    row.enabled = True
    await session.flush()
    return row, key


async def list_pending_screen_requests(session: AsyncSession, activity_id: UUID) -> list[ScreenKeyRow]:
    result = await session.scalars(
        select(ScreenKeyRow)
        .where(ScreenKeyRow.activity_id == activity_id, ScreenKeyRow.enabled.is_(False))
        .order_by(ScreenKeyRow.created_at.desc())
    )
    return list(result)
