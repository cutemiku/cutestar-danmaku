from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActivityStatus(StrEnum):
    DRAFT = "draft"
    LIVE = "live"
    PAUSED = "paused"
    CLOSED = "closed"


class DanmakuStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REVOKED = "revoked"
    BLOCKED = "blocked"


class DanmakuColorMode(StrEnum):
    FIXED = "fixed"
    RANDOM = "random"


COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class Activity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    public_code: str
    status: ActivityStatus = ActivityStatus.LIVE
    submission_paused: bool = False
    slow_mode_seconds: int = Field(default=0, ge=0, le=3600)
    danmaku_color_mode: DanmakuColorMode = DanmakuColorMode.FIXED
    danmaku_default_color: str = Field(default="#FFFFFF", pattern=COLOR_PATTERN)
    allow_custom_color: bool = False
    auto_moderation_enabled: bool = False
    allow_multiline: bool = False
    overlay_font_size: int = Field(default=28, ge=12, le=160)
    overlay_speed: int = Field(default=80, ge=10, le=1000)
    overlay_opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    overlay_font: str = Field(default="Segoe UI", max_length=64)
    created_at: datetime = Field(default_factory=utc_now)


class JoinRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)


class JoinResponse(BaseModel):
    participant_id: UUID
    activity_id: UUID
    nickname: str
    session_token: str


class DanmakuCreate(BaseModel):
    activity_id: UUID
    content: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    device_fingerprint: str | None = Field(default=None, min_length=8, max_length=128)


class BanTargetType(StrEnum):
    PARTICIPANT = "participant"
    IP = "ip"
    FINGERPRINT = "fingerprint"


class BanCreate(BaseModel):
    target_type: BanTargetType
    target_value: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=256)
    # 禁言时长（分钟）；为空表示永久禁言
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)


class Ban(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID
    target_type: BanTargetType
    target_value: str
    reason: str | None = None
    banned_by: str
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ScreenKeyCreate(BaseModel):
    """申请大屏授权密钥。"""

    label: str = Field(default="", max_length=64)


class ScreenKey(BaseModel):
    """大屏授权密钥记录。key 字段仅在申请响应中返回一次，后续不可再查。"""

    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID
    label: str = ""
    device_id: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    key: str | None = None


class ScreenRequestStatus(BaseModel):
    """大屏设备授权状态查询结果（公开端点，按 device_id）。"""

    status: str  # pending / approved / rejected / unknown
    key: str | None = None


class DanmakuLogItem(BaseModel):
    """后台弹幕日志条目：含发送人身份信息，用于溯源与禁言。"""

    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID
    participant_id: UUID
    nickname: str | None = None
    content: str
    color: str = Field(pattern=COLOR_PATTERN)
    status: DanmakuStatus = DanmakuStatus.PENDING
    ip_address: str | None = None
    device_fingerprint: str | None = None
    submitted_at: datetime = Field(default_factory=utc_now)


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    public_code: str = Field(pattern=r"^[A-Za-z0-9]{3,32}$")


class ActivityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: ActivityStatus | None = None
    auto_moderation_enabled: bool | None = None
    allow_multiline: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("活动名称不能为空")
        return value


class DanmakuSettings(BaseModel):
    color_mode: DanmakuColorMode
    default_color: str = Field(pattern=COLOR_PATTERN)
    allow_custom_color: bool


class OverlaySettings(BaseModel):
    """大屏显示设置：由服务端统一下发给大屏客户端。"""

    font_size: int = Field(ge=12, le=160)
    speed: int = Field(ge=10, le=1000)
    opacity: float = Field(ge=0.1, le=1.0)
    font: str = Field(min_length=1, max_length=64)


class Danmaku(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID
    participant_id: UUID
    content: str
    color: str = Field(pattern=COLOR_PATTERN)
    status: DanmakuStatus = DanmakuStatus.PENDING
    submitted_at: datetime = Field(default_factory=utc_now)


class ControlRequest(BaseModel):
    action: str = Field(pattern="^(pause_submissions|resume_submissions|slow_mode|clear_screen)$")
    seconds: int = Field(default=0, ge=0, le=3600)


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    sequence: int
    activity_id: UUID
    type: str
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, object]
