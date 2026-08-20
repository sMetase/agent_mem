# -*- coding: utf-8 -*-
"""
数据校验与标准化服务 — 角色A核心模块。

职责（对齐《核心业务逻辑拆解》第三节）：
1. 格式与完整性校验：必填字段、字段类型、时间格式、ID格式
2. 数据标准化：时间统一→ISO 8601、ID去空格/统一小写、元数据补全
3. 业务规则校验：独属于"接入层"的规则，不涉及LLM抽取
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.exceptions import ValidationError
from app.core.logger import get_logger

logger = get_logger("validation_service")

# ISO 8601 时间格式正则（支持带时区和不带时区的格式）
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"                     # YYYY-MM-DD
    r"[T ]\d{2}:\d{2}:\d{2}"                  # HH:MM:SS
    r"(?:\.\d+)?"                               # 可选毫秒
    r"(?:Z|[+-]\d{2}:\d{2})?$"                 # 可选时区
)

# ID 合法字符正则（字母数字、下划线、连字符）
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")

# 合法 role 值
VALID_ROLES = {"user", "agent", "system", "tool", "assistant"}

# 合法 interaction_type 值
VALID_INTERACTION_TYPES = {"dialogue", "session", "task_process"}

# 必填字段
REQUIRED_FIELDS = ["user_id", "content", "session_id"]

# ID 最大长度
MAX_ID_LENGTH = 128
MAX_CONTENT_LENGTH = 50000
MAX_SESSION_SUMMARY_LENGTH = 10000
MAX_TASK_FIELD_LENGTH = 5000


class ValidationResult:
    """校验结果容器"""

    def __init__(self, is_valid: bool = True, errors: Optional[list[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []

    def add_error(self, error: str) -> None:
        self.is_valid = False
        self.errors.append(error)

    def raise_if_invalid(self) -> None:
        if not self.is_valid:
            raise ValidationError(
                code="INVALID_PARAM",
                message="数据校验失败",
                detail={"errors": self.errors},
            )


# ============================================================
# 格式与完整性校验
# ============================================================

def validate_required_fields(data: dict) -> ValidationResult:
    """
    校验必填字段是否存在且非空。

    必填字段：user_id, content, session_id
    注：timestamp 缺失时由服务端补全，不在此拒绝
    """
    result = ValidationResult()
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            result.add_error(f"缺少必填字段: {field}")
    return result


def validate_field_types(data: dict) -> ValidationResult:
    """校验字段类型是否合法"""
    result = ValidationResult()

    # user_id 必须是字符串
    user_id = data.get("user_id")
    if user_id is not None and not isinstance(user_id, str):
        result.add_error(f"user_id 类型错误: 期望 str, 实际 {type(user_id).__name__}")

    # content 必须是字符串
    content = data.get("content")
    if content is not None and not isinstance(content, str):
        result.add_error(f"content 类型错误: 期望 str, 实际 {type(content).__name__}")

    # timestamp 如果提供了，校验格式
    timestamp = data.get("timestamp")
    if timestamp is not None:
        if isinstance(timestamp, str):
            if not ISO8601_RE.match(timestamp):
                result.add_error(
                    f"timestamp 格式错误: '{timestamp}'，"
                    f"期望 ISO 8601 格式，如 '2026-07-06T10:00:00Z'"
                )
        elif isinstance(timestamp, datetime):
            pass  # datetime 对象合法
        else:
            result.add_error(f"timestamp 类型错误: 期望 str(ISO 8601) 或 datetime")

    # role 必须是合法枚举值
    role = data.get("role")
    if role is not None:
        role_str = role.value if hasattr(role, "value") else str(role)
        if role_str not in VALID_ROLES:
            result.add_error(
                f"role 值非法: '{role_str}'，合法值: {', '.join(sorted(VALID_ROLES))}"
            )

    # interaction_type 必须是合法枚举值
    itype = data.get("interaction_type")
    if itype is not None:
        itype_str = itype.value if hasattr(itype, "value") else str(itype)
        if itype_str not in VALID_INTERACTION_TYPES:
            result.add_error(
                f"interaction_type 值非法: '{itype_str}'，"
                f"合法值: {', '.join(sorted(VALID_INTERACTION_TYPES))}"
            )

    # session_id 必须是字符串
    session_id = data.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        result.add_error(f"session_id 类型错误: 期望 str")

    return result


def validate_id_format(field_name: str, value: str) -> Optional[str]:
    """
    校验ID字段格式：合法字符 + 长度限制。
    返回错误信息字符串，合法时返回 None。
    """
    if not value:
        return f"{field_name} 不能为空"
    if len(value) > MAX_ID_LENGTH:
        return f"{field_name} 长度超过限制 ({len(value)} > {MAX_ID_LENGTH})"
    if not ID_PATTERN.match(value):
        return f"{field_name} 包含非法字符: '{value}'，仅允许字母、数字、下划线、连字符"
    return None


def validate_content_length(content: str) -> Optional[str]:
    """校验内容长度"""
    if len(content) > MAX_CONTENT_LENGTH:
        return f"content 长度超过限制 ({len(content)} > {MAX_CONTENT_LENGTH})"
    return None


# ============================================================
# 数据标准化
# ============================================================

def standardize_timestamp(value: Any) -> datetime:
    """
    统一时间格式为 UTC datetime 对象。

    - ISO 8601 字符串 → datetime (UTC)
    - datetime 对象 → 如果无时区则标记为 UTC
    - None → 当前 UTC 时间
    """
    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        value = value.strip()
        # 替换 T 前面的空格（某些客户端可能发送 "2026-07-06 10:00:00"）
        normalized = value.replace(" ", "T", 1) if "T" not in value else value
        # 兼容 Z 后缀（Python < 3.11 的 fromisoformat 不支持 Z）
        normalized = normalized.replace("Z", "+00:00")
        try:
            # Python 3.11+ fromisoformat 支持更广泛的 ISO 8601 格式
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            logger.warning(f"无法解析时间字符串: {value}，使用当前时间")
            return datetime.now(timezone.utc)

    # 无法处理的类型，使用当前时间
    logger.warning(f"无法处理的 timestamp 类型: {type(value).__name__}，使用当前时间")
    return datetime.now(timezone.utc)


def normalize_id(value: Optional[str]) -> Optional[str]:
    """
    ID 字段标准化：去前后空格 + 统一小写。
    """
    if value is None:
        return None
    return value.strip().lower()


def fill_default_metadata(data: dict, agent_id: Optional[str] = None,
                          scene_id: Optional[str] = None) -> dict:
    """
    补全元数据默认值。

    设计文档要求：对非核心但系统需要的元数据，自动补全默认值。
    """
    # 确保 business_meta 存在
    if "business_meta" not in data or data["business_meta"] is None:
        data["business_meta"] = {}

    meta = data["business_meta"]

    # 补全来源元数据
    if "source" not in meta:
        meta["source"] = "api"
    if "write_mode" not in meta:
        meta["write_mode"] = "sync"
    if "agent_id" not in meta and agent_id:
        meta["agent_id"] = agent_id
    if "scene_id" not in meta and scene_id:
        meta["scene_id"] = scene_id

    data["business_meta"] = meta
    return data


def generate_record_id() -> str:
    """生成交互记录 ID"""
    return f"rec_{uuid4().hex[:24]}"


# ============================================================
# 一站式校验+标准化
# ============================================================

def validate_and_standardize(
    data: dict,
    agent_id: Optional[str] = None,
    scene_id: Optional[str] = None,
) -> dict:
    """
    一站式数据校验与标准化管线。

    执行顺序：
    1. 必填字段校验
    2. 字段类型校验
    3. ID 格式校验
    4. 内容长度校验
    5. 时间戳标准化
    6. ID 标准化
    7. 元数据补全

    返回标准化后的数据字典。
    校验失败时抛出 ValidationError。
    """
    # 1. 必填字段
    result = validate_required_fields(data)
    result.raise_if_invalid()

    # 2. 字段类型
    result = validate_field_types(data)
    result.raise_if_invalid()

    # 3. ID 格式校验
    for id_field in ["user_id", "session_id", "task_id"]:
        value = data.get(id_field)
        if value and isinstance(value, str):
            err = validate_id_format(id_field, value)
            if err:
                result.add_error(err)
    result.raise_if_invalid()

    # 4. 内容长度
    content = data.get("content")
    if content and isinstance(content, str):
        err = validate_content_length(content)
        if err:
            result.add_error(err)
    result.raise_if_invalid()

    # 5. 时间戳标准化
    data["timestamp_dt"] = standardize_timestamp(data.get("timestamp"))

    # 6. ID 标准化
    data["user_id"] = normalize_id(data.get("user_id"))
    data["session_id"] = normalize_id(data.get("session_id"))
    if data.get("task_id"):
        data["task_id"] = normalize_id(data["task_id"])

    # 7. 元数据补全
    data = fill_default_metadata(data, agent_id=agent_id, scene_id=scene_id)

    # 8. 生成 record_id
    data["record_id"] = generate_record_id()

    # 注入 agent_id 和 scene_id
    if agent_id and not data.get("agent_id"):
        data["agent_id"] = agent_id
    if scene_id and not data.get("scene_id"):
        data["scene_id"] = scene_id

    logger.info(
        f"数据校验与标准化完成: record_id={data['record_id']}, "
        f"user_id={data['user_id']}, session_id={data['session_id']}"
    )

    return data


# ============================================================
# MemoryWriteRequest 类型感知校验
# ============================================================

def validate_write_request_by_type(
    interaction_type: str,
    messages: list,
    session_summary: str | None = None,
    session_time: str | None = None,
    task_goal: str | None = None,
    task_progress: str | None = None,
    task_result: str | None = None,
) -> ValidationResult:
    """
    根据 interaction_type 对写入请求进行差异化校验。

    规则：
    - dialogue:      messages 不能为空
    - session:       messages 或 session_summary 至少有一个
    - task_process:  messages 或 task_goal/task_progress/task_result 至少有一个
    """
    result = ValidationResult()

    if interaction_type == "dialogue":
        if not messages:
            result.add_error("dialogue 类型必须提供 messages 数组")

    elif interaction_type == "session":
        has_messages = bool(messages)
        has_summary = bool(session_summary and session_summary.strip())
        if not has_messages and not has_summary:
            result.add_error("session 类型必须提供 messages 或 session_summary")
        if session_time:
            err = _validate_iso8601(session_time)
            if err:
                result.add_error(f"session_time 格式错误: {err}")
        if session_summary and len(session_summary) > MAX_SESSION_SUMMARY_LENGTH:
            result.add_error(
                f"session_summary 长度超过限制 ({len(session_summary)} > {MAX_SESSION_SUMMARY_LENGTH})"
            )

    elif interaction_type == "task_process":
        has_messages = bool(messages)
        has_task_data = bool(
            (task_goal and task_goal.strip()) or
            (task_progress and task_progress.strip()) or
            (task_result and task_result.strip())
        )
        if not has_messages and not has_task_data:
            result.add_error(
                "task_process 类型必须提供 messages 或 task_goal/task_progress/task_result"
            )
        for field_name, value in [
            ("task_goal", task_goal),
            ("task_progress", task_progress),
            ("task_result", task_result),
        ]:
            if value and len(value) > MAX_TASK_FIELD_LENGTH:
                result.add_error(
                    f"{field_name} 长度超过限制 ({len(value)} > {MAX_TASK_FIELD_LENGTH})"
                )

    return result


def _validate_iso8601(value: str) -> str | None:
    """校验 ISO 8601 时间格式，返回错误信息或 None"""
    try:
        from datetime import datetime
        # 尝试解析
        normalized = value.strip().replace(" ", "T", 1) if "T" not in value else value.strip()
        # 兼容 Z 后缀（Python < 3.11 的 fromisoformat 不支持 Z）
        normalized = normalized.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
        return None
    except (ValueError, TypeError) as e:
        return str(e)
