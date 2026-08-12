import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CUTESTAR_", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+asyncpg://cutestar:cutestar@localhost:5432/cutestar"
    redis_url: str = ""
    # 逗号分隔的 CORS 白名单（pydantic-settings 对 list 字段会先尝试 JSON 解析，故用字符串存储）
    cors_origins: str = "http://localhost:5173,http://localhost:4173"
    jwt_secret: str = ""
    jwt_expire_minutes: int = 480
    admin_username: str = "admin"
    admin_password: str = ""
    # Frontend and backend must share this opaque route segment.
    admin_entry_path: str = "ops-console-7f3a"

    # 阿里云内容安全配置（默认空：未配置时自动审核降级为人工复核，见 moderation.py）
    alibaba_access_key_id: str = ""
    alibaba_access_key_secret: str = ""
    alibaba_green_endpoint: str = "green-cip.cn-shanghai.aliyuncs.com"
    alibaba_green_service: str = "comment_detection"  # 公聊评论检测

    @field_validator("admin_entry_path")
    @classmethod
    def validate_admin_entry_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}", value):
            raise ValueError("CUTESTAR_ADMIN_ENTRY_PATH must be 8-64 URL-safe characters")
        if value.lower() in {"admin", "login", "api", "control-room"}:
            raise ValueError("CUTESTAR_ADMIN_ENTRY_PATH is too predictable")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        """JWT 密钥不得为空或可预测默认值：生产环境必须由 .env 提供强随机值。"""
        value = value.strip()
        if not value:
            raise ValueError("CUTESTAR_JWT_SECRET 未配置：请生成强随机值写入 server/.env")
        if value in {"dev-only-secret-change-me", "change-me", "secret"} or len(value) < 32:
            raise ValueError("CUTESTAR_JWT_SECRET 过弱：至少 32 字符的强随机值")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
