from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import utc_now


class Base(DeclarativeBase):
    pass


class ActivityRow(Base):
    __tablename__ = "activities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    public_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="live")
    submission_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    slow_mode_seconds: Mapped[int] = mapped_column(Integer, default=0)
    danmaku_color_mode: Mapped[str] = mapped_column(String(16), default="fixed")
    danmaku_default_color: Mapped[str] = mapped_column(String(16), default="#FFFFFF")
    allow_custom_color: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_moderation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_multiline: Mapped[bool] = mapped_column(Boolean, default=False)
    overlay_font_size: Mapped[int] = mapped_column(Integer, default=28)
    overlay_speed: Mapped[int] = mapped_column(Integer, default=80)
    overlay_opacity: Mapped[float] = mapped_column(Float, default=1.0)
    overlay_font: Mapped[str] = mapped_column(String(64), default="Segoe UI")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ParticipantRow(Base):
    __tablename__ = "participants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("activities.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(24))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DanmakuRow(Base):
    __tablename__ = "danmaku"
    __table_args__ = (UniqueConstraint("activity_id", "idempotency_key", name="uq_danmaku_activity_idempotency"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("activities.id"), index=True)
    participant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("participants.id"))
    content: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(16), default="#FFFFFF")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BanRow(Base):
    """禁言记录：按发送人 / IP / 设备指纹维度封禁，expires_at 为空表示永久。"""

    __tablename__ = "bans"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("activities.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16))
    target_value: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    banned_by: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScreenKeyRow(Base):
    """大屏授权密钥：两种来源——
    1) 手动申请（device_id 为空，enabled 即用）
    2) 设备请求（device_id 非空：首次连接自动注册待审批，管理员批准后生成 sk 并 enabled）

    key_hash 存 SHA-256（十六进制），明文仅在申请/批准响应中出现一次。
    """

    __tablename__ = "screen_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("activities.id"), index=True)
    key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    # 设备流程（device_id 非空）专用：明文 sk 仅授权后写入，供大屏凭 device_id 领取。
    # 手动申请（device_id 为空）不落明文，一次性响应后仅存哈希。
    key_plain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    device_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("activities.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminRow(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
