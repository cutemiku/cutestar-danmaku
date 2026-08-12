"""阿里云内容安全文本审核集成。"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from .config import settings

logger = logging.getLogger("cutestar.moderation")


class ModerationVerdict(str, Enum):
    PASSED = "passed"    # 安全，自动通过
    REJECTED = "rejected"  # 高风险，自动拒绝
    REVIEW = "review"    # 中/低风险，人工复核


@dataclass
class ModerationResult:
    verdict: ModerationVerdict
    labels: str = ""
    risk_level: str = ""
    risk_words: str = ""


@lru_cache(maxsize=1)
def _create_client():
    """延迟创建 SDK 客户端（缓存单例）：首次调用导入 SDK 全家桶较慢（秒级），
    后续复用同一 Client 与底层连接，避免每条弹幕冷启动。"""
    from alibabacloud_green20220302.client import Client
    from alibabacloud_tea_openapi.models import Config

    config = Config(
        access_key_id=settings.alibaba_access_key_id,
        access_key_secret=settings.alibaba_access_key_secret,
        endpoint=settings.alibaba_green_endpoint,
        region_id="cn-shanghai",
        connect_timeout=5000,
        read_timeout=10000,
    )
    return Client(config)


async def warmup() -> None:
    """启动预热：在后台执行一次真实调用，加载 SDK 并建立到阿里云的连接，
    使首条弹幕不再触发秒级冷启动。未配置密钥时静默跳过。"""
    if not settings.alibaba_access_key_id or not settings.alibaba_access_key_secret:
        logger.info("阿里云内容安全未配置 AccessKey，跳过预热")
        return
    try:
        await asyncio.wait_for(asyncio.to_thread(_check_content_sync, "warmup"), timeout=20)
        logger.info("阿里云内容安全 SDK 预热完成")
    except Exception:
        logger.warning("阿里云内容安全 SDK 预热失败（不影响启动）", exc_info=True)


def _check_content_sync(text: str) -> ModerationResult:
    """同步调用阿里云 TextModeration API（在线程池中运行）。"""
    from alibabacloud_green20220302 import models as green_models
    from alibabacloud_tea_util.client import Client as UtilClient
    from alibabacloud_tea_util import models as util_models

    client = _create_client()
    service_parameters = json.dumps({"content": text}, ensure_ascii=False)
    request = green_models.TextModerationRequest(
        service=settings.alibaba_green_service,
        service_parameters=service_parameters,
    )
    runtime = util_models.RuntimeOptions()
    runtime.read_timeout = 10000
    runtime.connect_timeout = 10000

    response = client.text_moderation_with_options(request, runtime)

    # 自动路由：服务端错误时切换到 cn-beijing
    if UtilClient.equal_number(500, response.status_code) or not response or not response.body or 200 != response.body.code:
        from alibabacloud_tea_openapi.models import Config
        config = Config(
            access_key_id=settings.alibaba_access_key_id,
            access_key_secret=settings.alibaba_access_key_secret,
            endpoint="green-cip.cn-beijing.aliyuncs.com",
            region_id="cn-beijing",
            connect_timeout=5000,
            read_timeout=10000,
        )
        client = _create_client.__wrapped__() if hasattr(_create_client, '__wrapped__') else __import__('alibabacloud_green20220302.client', fromlist=['Client']).Client(config)
        response = client.text_moderation_with_options(request, runtime)

    if response.status_code != 200 or not response.body:
        return ModerationResult(verdict=ModerationVerdict.REVIEW, risk_level="unknown")

    result = response.body
    if result.code != 200:
        return ModerationResult(verdict=ModerationVerdict.REVIEW, risk_level="unknown")

    data = result.data
    labels = data.labels or ""

    # 解析 riskLevel
    risk_level = ""
    risk_words = ""
    if data.reason:
        try:
            reason = json.loads(data.reason)
            risk_level = reason.get("riskLevel", "")
            risk_words = reason.get("riskWords", "")
        except (json.JSONDecodeError, AttributeError):
            pass

    # 判定逻辑
    if not labels:
        verdict = ModerationVerdict.PASSED
    elif risk_level == "high":
        verdict = ModerationVerdict.REJECTED
    else:
        verdict = ModerationVerdict.REVIEW  # medium/low → 人工复核

    return ModerationResult(
        verdict=verdict,
        labels=labels,
        risk_level=risk_level,
        risk_words=risk_words,
    )


async def check_content(text: str) -> ModerationResult:
    """异步调用内容安全审核。API 异常时降级为人工复核。"""
    if not settings.alibaba_access_key_id or not settings.alibaba_access_key_secret:
        logger.warning("阿里云内容安全未配置 AccessKey，跳过自动审核")
        return ModerationResult(verdict=ModerationVerdict.REVIEW, risk_level="not_configured")

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_check_content_sync, text),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("阿里云内容安全 API 超时，降级为人工复核")
        return ModerationResult(verdict=ModerationVerdict.REVIEW, risk_level="timeout")
    except Exception as e:
        logger.error("阿里云内容安全 API 调用失败: %s", e, exc_info=True)
        return ModerationResult(verdict=ModerationVerdict.REVIEW, risk_level="error")
