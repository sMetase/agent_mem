# -*- coding: utf-8 -*-
"""
Dashboard 聚合服务 — 全局统计数据查询与缓存。

实现说明：
  1. 所有查询共享同一 as_of 快照时间，保证一致性
  2. 顺序执行（同一 AsyncSession 不支持并发查询）
  3. 30s 模块级缓存，加锁保护
  4. 核心查询失败时传播异常，不由本层静默降级
"""
import copy
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.base import (
    Agent, ApiLog, DedupAudit, Memory, RetrievalRequest, RetrievalResult,
    Scene, Task,
)
from app.schemas.dashboard import (
    DashboardComparison, DashboardData, DashboardSummary,
    GenerationSummary, LatestContext, RecentAgentItem, RecentAlertItem,
    RecentRetrievalItem, RecentTaskItem, RetrievalSignalItem,
    TrendItem, TypeDistributionItem,
)

logger = get_logger("dashboard_service")

# ── 模块级缓存 ──────────────────────────────────────────────
_cache: dict[str, tuple[float, DashboardData]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 30          # 缓存有效期（秒）
_MAX_CACHE_ITEMS = 20    # 最大缓存条目


def _cache_key(hours: int, trend_days: int) -> str:
    return f"dash:{hours}:{trend_days}"


def _get_cached(key: str) -> DashboardData | None:
    """获取缓存（过期或不存在返回 None）。"""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return copy.deepcopy(data)


def _set_cache(key: str, data: DashboardData) -> None:
    """写入缓存并控制大小。"""
    if len(_cache) >= _MAX_CACHE_ITEMS:
        oldest_key = min(_cache.keys(), key=lambda k: _cache[k][0])
        del _cache[oldest_key]
    _cache[key] = (time.monotonic(), copy.deepcopy(data))


# ── 计数工具 ────────────────────────────────────────────────
async def _count(db: AsyncSession, stmt) -> int:
    result = await db.execute(stmt)
    return result.scalar() or 0


# ── Summary ─────────────────────────────────────────────────
async def _compute_summary(
    db: AsyncSession, as_of: datetime, current_start: datetime,
) -> DashboardSummary:
    logger.info("Computing dashboard summary")

    agent_count = await _count(
        db, select(func.count()).select_from(Agent).where(
            Agent.is_active == True,
            Agent.created_at < as_of,
        )
    )
    scene_count = await _count(
        db, select(func.count()).select_from(Scene).where(
            Scene.is_active == True,
            Scene.created_at < as_of,
        )
    )
    memory_count = await _count(
        db, select(func.count()).select_from(Memory).where(
            Memory.created_at < as_of,
            Memory.status != "deleted",
            (Memory.deleted_at.is_(None)) | (Memory.deleted_at >= as_of),
        )
    )
    retrieval_count = await _count(
        db, select(func.count()).select_from(RetrievalRequest).where(
            RetrievalRequest.created_at >= current_start,
            RetrievalRequest.created_at < as_of,
        )
    )

    # context_success_rate: 窗口内 /api/v1/memory/context 的成功率
    total_ctx = await _count(
        db, select(func.count()).select_from(ApiLog).where(
            ApiLog.api_path == "/api/v1/memory/context",
            ApiLog.created_at >= current_start,
            ApiLog.created_at < as_of,
        )
    )
    if total_ctx == 0:
        ctx_rate = None
    else:
        ok_ctx = await _count(
            db, select(func.count()).select_from(ApiLog).where(
                ApiLog.api_path == "/api/v1/memory/context",
                ApiLog.response_code >= 200,
                ApiLog.response_code < 300,
                ApiLog.created_at >= current_start,
                ApiLog.created_at < as_of,
            )
        )
        ctx_rate = round(ok_ctx / total_ctx, 4)

    return DashboardSummary(
        agent_count=agent_count,
        scene_count=scene_count,
        memory_count=memory_count,
        retrieval_count=retrieval_count,
        context_success_rate=ctx_rate,
    )


# ── Comparison ──────────────────────────────────────────────
async def _compute_comparison(
    db: AsyncSession, as_of: datetime,
    current_start: datetime, prev_start: datetime, prev_end: datetime,
) -> DashboardComparison:
    logger.info("Computing dashboard comparison")

    # --- 存量指标：as_of vs current_start 快照 ---
    def _growth_rate(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous, 4)

    # Agent（若无停用时间，previous 无法精确还原，返回 None）
    try:
        agent_now = await _count(
            db, select(func.count()).select_from(Agent).where(
                Agent.is_active == True, Agent.created_at < as_of,
            )
        )
        agent_prev = await _count(
            db, select(func.count()).select_from(Agent).where(
                Agent.is_active == True, Agent.created_at < current_start,
            )
        )
        agent_rate = _growth_rate(agent_now, agent_prev)
    except Exception:
        logger.warning("Agent comparison unavailable (no deactivation audit)")
        agent_rate = None

    # Scene
    try:
        scene_now = await _count(
            db, select(func.count()).select_from(Scene).where(
                Scene.is_active == True, Scene.created_at < as_of,
            )
        )
        scene_prev = await _count(
            db, select(func.count()).select_from(Scene).where(
                Scene.is_active == True, Scene.created_at < current_start,
            )
        )
        scene_rate = _growth_rate(scene_now, scene_prev)
    except Exception:
        logger.warning("Scene comparison unavailable")
        scene_rate = None

    # Memory（支持 deleted_at 历史快照）
    # 历史查询不能加 status != 'deleted'：会排除在快照时刻仍活跃、后续才被删除的记录。
    # 但缺失 deleted_at 的迁移前已删记录会被计入，这是已知限制。
    def _mem_count(as_of_ts: datetime) -> int:
        return _count(
            db, select(func.count()).select_from(Memory).where(
                Memory.created_at < as_of_ts,
                (Memory.deleted_at.is_(None)) | (Memory.deleted_at >= as_of_ts),
            )
        )

    try:
        mem_now = await _mem_count(as_of)
        mem_prev = await _mem_count(current_start)
        mem_rate = _growth_rate(mem_now, mem_prev)
    except Exception:
        logger.warning("Memory comparison unavailable")
        mem_rate = None

    # --- 窗口指标 ---
    # Retrieval
    ret_now = await _count(
        db, select(func.count()).select_from(RetrievalRequest).where(
            RetrievalRequest.created_at >= current_start,
            RetrievalRequest.created_at < as_of,
        )
    )
    ret_prev = await _count(
        db, select(func.count()).select_from(RetrievalRequest).where(
            RetrievalRequest.created_at >= prev_start,
            RetrievalRequest.created_at < prev_end,
        )
    )
    ret_rate = _growth_rate(ret_now, ret_prev)

    # Context success rate change
    async def _ctx_rate(start: datetime, end: datetime) -> float | None:
        t = await _count(
            db, select(func.count()).select_from(ApiLog).where(
                ApiLog.api_path == "/api/v1/memory/context",
                ApiLog.created_at >= start,
                ApiLog.created_at < end,
            )
        )
        if t == 0:
            return None
        ok = await _count(
            db, select(func.count()).select_from(ApiLog).where(
                ApiLog.api_path == "/api/v1/memory/context",
                ApiLog.response_code >= 200,
                ApiLog.response_code < 300,
                ApiLog.created_at >= start,
                ApiLog.created_at < end,
            )
        )
        return ok / t

    curr_rate = await _ctx_rate(current_start, as_of)
    prev_rate = await _ctx_rate(prev_start, prev_end)
    if curr_rate is None or prev_rate is None:
        ctx_change = None
    else:
        ctx_change = round(curr_rate - prev_rate, 4)

    return DashboardComparison(
        agent_count_rate=agent_rate,
        scene_count_rate=scene_rate,
        memory_count_rate=mem_rate,
        retrieval_count_rate=ret_rate,
        context_success_rate_change=ctx_change,
    )


# ── Memory Trend ────────────────────────────────────────────
async def _compute_memory_trend(
    db: AsyncSession, as_of: datetime, trend_days: int,
) -> list:
    """
    按日趋势 — 半开区间 [day_start_utc, next_day_start_utc)。

    日末有效总量使用 deleted_at 快照：
      created_at < 快照时间 AND (deleted_at IS NULL OR deleted_at >= 快照时间)

    限制：迁移前已删除（status='deleted' 但 deleted_at=NULL）的记录
    会被视为"从未删除"而计入历史趋势。这是因为迁移前没有保留删除时间，
    无法准确还原历史总量。trend 数据从审计机制启用后完全准确，迁移前的
    趋势总量可能略高于实际值。

    时区: Asia/Shanghai 业务日。半开区间。
    """
    try:
        tz = ZoneInfo("Asia/Shanghai")
    except Exception:
        tz = timezone(timedelta(hours=8))  # Windows 无 IANA 时区库时回退为 UTC+8
    asof_shanghai = as_of.astimezone(tz)
    today = asof_shanghai.date()

    # 生成连续日期列表
    dates = [today - timedelta(days=i) for i in range(trend_days - 1, -1, -1)]

    def _day_bounds(d: date) -> tuple[datetime, datetime]:
        """返回 (day_start_utc, next_day_start_utc)。"""
        start_local = datetime(d.year, d.month, d.day, tzinfo=tz)
        next_local = start_local + timedelta(days=1)
        return (start_local.astimezone(timezone.utc), next_local.astimezone(timezone.utc))

    trend = []
    prev_total = 0

    for d in dates:
        day_start, next_start = _day_bounds(d)

        # 当日新增
        added = await _count(
            db, select(func.count()).select_from(Memory).where(
                Memory.created_at >= day_start,
                Memory.created_at < next_start,
            )
        )

        # 日末快照时间
        snap_end = min(next_start, as_of)

        # 日末有效总量
        total = await _count(
            db, select(func.count()).select_from(Memory).where(
                Memory.created_at < snap_end,
                (Memory.deleted_at.is_(None)) | (Memory.deleted_at >= snap_end),
            )
        )

        trend.append(TrendItem(date=d, total=total, added=added))
        prev_total = total

    return trend


# ── Generation Summary ─────────────────────────────────────
# DedupAudit.action → generation_summary 字段映射：
#
#   keep_new        → generated_count   新记忆，无重复
#   merge           → merged_count      与现有记忆融合
#   update_existing → updated_count     替换现有记忆内容
#   discard         → discarded_count   被判定为重复，丢弃
#   conflict        → conflict_count    无法自动裁决，标记冲突
#
# 以下情况不进入统计（_write_audit_trail 不写入审计记录）：
#   向量检索失败后默认保留          → 技术降级，非正常生成事件
#   LLM 去重判断异常                → 不写入审计
#   数据库查询失败后默认保留         → 不写入审计
#   重试导致重复审计                → 暂不处理，单次 Pipeline 不重试
#   SKIP（非去重模块的跳过）         → 不由此模块处理
# 一条 candidate 仅产生一次 _process_single → 一次审计，不会先 generated 再 merged。
_ACTION_MAP = {
    "keep_new": "generated_count",
    "merge": "merged_count",
    "update_existing": "updated_count",
    "discard": "discarded_count",
    "conflict": "conflict_count",
}


async def _compute_generation_summary(
    db: AsyncSession, current_start: datetime, as_of: datetime,
) -> GenerationSummary:
    logger.info("Computing generation summary")

    rows = (
        await db.execute(
            select(DedupAudit.action, func.count().label("cnt"))
            .where(
                DedupAudit.created_at >= current_start,
                DedupAudit.created_at < as_of,
            )
            .group_by(DedupAudit.action)
        )
    ).all()

    counts = {row.action: row.cnt for row in rows}
    return GenerationSummary(
        generated_count=counts.get("keep_new", 0),
        merged_count=counts.get("merge", 0),
        updated_count=counts.get("update_existing", 0),
        discarded_count=counts.get("discard", 0),
        conflict_count=counts.get("conflict", 0),
    )


# ── Retrieval Signal Distribution ─────────────────────────
# 当前记录的检索模式（retrieval_mode）：
#
#   hybrid  → Qdrant 向量检索 + PostgreSQL 元数据过滤
#             对应正常 search() 路径
#   keyword → DB-only 关键词/文本匹配
#             对应 _db_only_search() 降级路径（向量服务不可用时）
#
# 这些值反映了实际的检索执行路径，也是当前可区分的最细粒度信号。
# 若业务需要区分 semantic / keyword / metadata / hybrid 四种独立信号，
# 需要重构检索层使其分别记录各信号类型及其权重贡献。
_ACTION_MAP_RS = {
    "hybrid": "语义+关键词混合检索",
    "keyword": "关键词检索（向量降级）",
}


async def _compute_retrieval_signal_distribution(
    db: AsyncSession, current_start: datetime, as_of: datetime,
) -> list[RetrievalSignalItem]:
    logger.info("Computing retrieval signal distribution")

    rows = (
        await db.execute(
            select(
                RetrievalRequest.retrieval_mode,
                func.count().label("cnt"),
            )
            .where(
                RetrievalRequest.retrieval_mode.isnot(None),
                RetrievalRequest.created_at >= current_start,
                RetrievalRequest.created_at < as_of,
            )
            .group_by(RetrievalRequest.retrieval_mode)
            .order_by(func.count().desc())
        )
    ).all()

    total = sum(row.cnt for row in rows)
    if total == 0:
        return []

    return [
        RetrievalSignalItem(
            signal=row.retrieval_mode,
            count=row.cnt,
            ratio=round(row.cnt / total, 4),
        )
        for row in rows
    ]


# ── Type Distribution ──────────────────────────────────────
async def _compute_type_distribution(
    db: AsyncSession, as_of: datetime,
) -> list[TypeDistributionItem]:
    logger.info("Computing memory type distribution")

    effective = (Memory.deleted_at.is_(None)) | (Memory.deleted_at >= as_of)
    rows = (
        await db.execute(
            select(
                func.coalesce(Memory.memory_type, "unknown").label("memory_type"),
                func.count().label("count"),
            )
            .where(Memory.created_at < as_of, effective)
            .group_by(text("memory_type"))
            .order_by(text("count DESC"), text("memory_type ASC"))
        )
    ).all()

    total = sum(row.count for row in rows)
    if total == 0:
        return []

    return [
        TypeDistributionItem(
            memory_type=row.memory_type,
            count=row.count,
            ratio=round(row.count / total, 4),
        )
        for row in rows
    ]


# ── 脱敏工具 ────────────────────────────────────────────────
import re

_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号]"),
    (re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b"), "[邮箱]"),
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|sk-)[\s:=]+[^\s,;\"]{8,}"), r"\1***"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[身份证]"),
]


def _desensitize(text: str, max_len: int = 120) -> str:
    if not text:
        return ""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    text = " ".join(text.split())  # 规范化空白
    return text[:max_len]


# ── Recent Agents ───────────────────────────────────────────
async def _compute_recent_agents(
    db: AsyncSession, as_of: datetime,
) -> list[RecentAgentItem]:
    """通过 t_memory 找出最近有写入的 agent，最多 5 条。"""
    rows = (
        await db.execute(
            select(
                Memory.agent_id,
                func.max(Memory.created_at).label("last_write"),
            )
            .where(
                Memory.agent_id.isnot(None),
                Memory.agent_id != "",
                Memory.created_at < as_of,
            )
            .group_by(Memory.agent_id)
            .order_by(func.max(Memory.created_at).desc(), Memory.agent_id.asc())
            .limit(5)
        )
    ).all()

    result = []
    for row in rows:
        scene_id_val = None
        scene_name = None
        if row.agent_id:
            agent = await db.execute(
                select(Agent.scene_id).where(Agent.agent_id == row.agent_id)
            )
            scene_id_val = agent.scalar_one_or_none()
            if scene_id_val:
                scene = await db.execute(
                    select(Scene.scene_name).where(Scene.scene_id == scene_id_val)
                )
                scene_name = scene.scalar_one_or_none()

        result.append(RecentAgentItem(
            agent_id=row.agent_id,
            scene_id=scene_id_val,
            scene_name=scene_name,
            status="active",
            last_write_at=row.last_write.isoformat() if row.last_write else None,
            latest_result=None,
        ))

    return result


# ── Recent Retrievals ───────────────────────────────────────
async def _compute_recent_retrievals(
    db: AsyncSession, as_of: datetime,
) -> list[RecentRetrievalItem]:
    """最近检索请求，关联首位结果取 memory_type 和 relevance_score。"""
    rows = (
        await db.execute(
            select(
                RetrievalRequest.request_id,
                RetrievalRequest.query_text,
                RetrievalRequest.created_at,
                RetrievalResult.memory_id,
                RetrievalResult.relevance_score,
            )
            .outerjoin(
                RetrievalResult,
                (RetrievalResult.request_id == RetrievalRequest.request_id)
                & (RetrievalResult.rank == 0),  # 首位结果
            )
            .where(RetrievalRequest.created_at < as_of)
            .order_by(RetrievalRequest.created_at.desc(), RetrievalRequest.request_id.asc())
            .limit(5)
        )
    ).all()

    result = []
    for row in rows:
        # 通过 memory_id 取 memory_type
        mem_type = None
        if row.memory_id:
            mem = await db.execute(
                select(Memory.memory_type).where(Memory.memory_id == row.memory_id)
            )
            mem_type = mem.scalar_one_or_none()

        result.append(RecentRetrievalItem(
            retrieval_id=row.request_id,
            memory_type=mem_type,
            summary=_desensitize(row.query_text or "", max_len=120),
            relevance_score=row.relevance_score,
            occurred_at=row.created_at.isoformat() if row.created_at else None,
        ))

    return result


# ── Recent Alerts ───────────────────────────────────────────
async def _compute_recent_alerts(
    db: AsyncSession, as_of: datetime, active_window: int = 30,
) -> list[RecentAlertItem]:
    """最近系统告警 — 取 error_code 非空的失败调用。

    每条告警根据错误后同一路径的请求记录判断状态：
      - resolved:   该错误后有同路径 2xx 成功请求
      - active:     最近 active_window 分钟内仍无成功请求，且是该路径最新记录
      - historical: 其他情况（旧记录、被更新错误覆盖等）
    """
    rows = (
        await db.execute(
            select(
                ApiLog.log_id,
                ApiLog.api_path,
                ApiLog.error_code,
                ApiLog.trace_id,
                ApiLog.created_at,
                ApiLog.response_code,
            )
            .where(
                ApiLog.error_code.isnot(None),
                ApiLog.error_code != "",
                ApiLog.created_at < as_of,
            )
            .order_by(ApiLog.created_at.desc(), ApiLog.log_id.desc())
            .limit(5)
        )
    ).all()

    if not rows:
        return []

    # 收集涉及的路径和最早期错误时间
    paths = {r.api_path for r in rows if r.api_path}
    earliest = min(r.created_at for r in rows)

    # 批量查询这些路径的后续日志（从最早错误时间开始）
    history_rows = (
        await db.execute(
            select(
                ApiLog.api_path,
                ApiLog.created_at,
                ApiLog.response_code,
            )
            .where(
                ApiLog.api_path.in_(paths),
                ApiLog.created_at >= earliest,
                ApiLog.created_at < as_of,
            )
            .order_by(ApiLog.api_path, ApiLog.created_at, ApiLog.log_id)
        )
    ).all()

    # 按路径组织时间线
    from collections import defaultdict
    timeline: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
    for r in history_rows:
        if r.api_path:
            timeline[r.api_path].append((r.created_at, r.response_code))

    # 判断每条告警的状态
    now = datetime.now(timezone.utc)
    alerts = []
    for r in rows:
        resolved_at = None
        status = "historical"

        path_events = timeline.get(r.api_path, [])
        later = [(t, code) for t, code in path_events if t > r.created_at]
        latest_for_path = path_events[-1] if path_events else None

        # 检查是否有后续成功
        first_success = next(((t, code) for t, code in later if 200 <= code < 300), None)
        if first_success is not None:
            status = "resolved"
            resolved_at = first_success[0]
        else:
            is_latest = (
                latest_for_path is not None
                and latest_for_path[0] == r.created_at
                and latest_for_path[1] == r.response_code
            )
            is_recent = (now - r.created_at).total_seconds() < active_window * 60
            if is_latest and is_recent:
                status = "active"

        alerts.append(RecentAlertItem(
            message=f"接口 {r.api_path} 调用失败 (HTTP {r.response_code})",
            api_path=r.api_path,
            error_code=r.error_code,
            trace_id=r.trace_id,
            occurred_at=r.created_at,
            status=status,
            resolved_at=resolved_at,
        ))

    # 后处理：同一路径多次失败被标记为 resolved 时，只保留最新一条
    # 避免同一次故障显示多条"已恢复告警"
    resolved_by_path: dict[str, bool] = {}
    for alert in alerts:
        if alert.status == "resolved" and alert.api_path:
            if alert.api_path in resolved_by_path:
                alert.status = "historical"
                alert.resolved_at = None
            else:
                resolved_by_path[alert.api_path] = True

    return alerts


# ── Latest Context ──────────────────────────────────────────
async def _compute_latest_context(
    db: AsyncSession, as_of: datetime,
) -> LatestContext | None:
    """最近一次成功上下文调用的快照。

    从 ApiLog 中查找最近一条成功 /api/v1/memory/context 记录，
    其 request_params 中必须包含 context_snapshot.version == 1。
    """
    # 取最近 20 条成功 /context 记录，在 Python 中寻找第一条有效快照。
    # 不把 JSON 过滤推到 SQL 层（避免 .astext 兼容问题），同时处理
    # "最新日志无快照、更早日志有快照" 的场景。
    rows = (
        await db.execute(
            select(ApiLog)
            .where(
                ApiLog.api_path == "/api/v1/memory/context",
                ApiLog.response_code >= 200,
                ApiLog.response_code < 300,
                ApiLog.request_params.isnot(None),
                ApiLog.created_at < as_of,
            )
            .order_by(ApiLog.created_at.desc(), ApiLog.log_id.desc())
            .limit(20)
        )
    ).scalars().all()

    for row in rows:
        params = row.request_params
        if not isinstance(params, dict):
            continue

        snap = params.get("context_snapshot")
        if not isinstance(snap, dict):
            continue

        if snap.get("version") not in (1, "1"):
            continue

        formatted_text = snap.get("formatted_text")
        if not isinstance(formatted_text, str) or not formatted_text.strip():
            continue

        generated_at_raw = snap.get("generated_at")
        if not generated_at_raw:
            continue

        generated_at = None
        try:
            generated_at = datetime.fromisoformat(str(generated_at_raw))
        except (ValueError, TypeError):
            generated_at = row.created_at

        return LatestContext(
            formatted_text=formatted_text,
            memory_count=int(snap.get("memory_count") or 0),
            query=snap.get("query"),
            return_mode=snap.get("return_mode"),
            scope_type=snap.get("scope_type"),
            user_id=snap.get("user_id"),
            agent_id=snap.get("agent_id"),
            scene_id=snap.get("scene_id"),
            session_id=snap.get("session_id"),
            task_id=snap.get("task_id"),
            generated_at=generated_at,
            trace_id=snap.get("trace_id") or row.trace_id,
        )

    return None


# ── Recent Tasks ────────────────────────────────────────────
async def _compute_recent_tasks(
    db: AsyncSession, as_of: datetime,
) -> list[RecentTaskItem]:
    """最近更新的任务。"""
    rows = (
        await db.execute(
            select(Task)
            .where(Task.started_at < as_of)
            .order_by(Task.updated_at.desc(), Task.task_id.asc())
            .limit(5)
        )
    ).scalars().all()

    return [
        RecentTaskItem(
            task_id=r.task_id,
            title=r.title,
            status=r.status,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


# ── 主入口 ──────────────────────────────────────────────────
async def get_dashboard_data(
    db: AsyncSession,
    hours: int = 24,
    trend_days: int = 7,
) -> DashboardData:
    """
    获取 Dashboard 聚合数据。

    参数校验在路由层完成，本函数假定已传入合法值。
    所有子查询共用同一 as_of 快照。
    """
    as_of = datetime.now(timezone.utc)
    current_start = as_of - timedelta(hours=hours)
    prev_start = as_of - timedelta(hours=2 * hours)
    prev_end = current_start

    key = _cache_key(hours, trend_days)
    with _cache_lock:
        cached = _get_cached(key)
        if cached is not None:
            logger.debug("Dashboard cache hit")
            return cached

    logger.info(
        f"Computing dashboard: hours={hours}, trend_days={trend_days}, "
        f"as_of={as_of.isoformat()}"
    )

    summary = await _compute_summary(db, as_of, current_start)
    comparison = await _compute_comparison(db, as_of, current_start, prev_start, prev_end)
    memory_trend = await _compute_memory_trend(db, as_of, trend_days)
    distribution = await _compute_type_distribution(db, as_of)
    generation = await _compute_generation_summary(db, current_start, as_of)
    signals = await _compute_retrieval_signal_distribution(db, current_start, as_of)
    recent_agents = await _compute_recent_agents(db, as_of)
    recent_retrievals = await _compute_recent_retrievals(db, as_of)
    recent_alerts = await _compute_recent_alerts(db, as_of)
    recent_tasks = await _compute_recent_tasks(db, as_of)
    latest_context = await _compute_latest_context(db, as_of)

    data = DashboardData(
        summary=summary,
        comparison=comparison,
        memory_trend=memory_trend,
        memory_type_distribution=distribution,
        generation_summary=generation,
        retrieval_signal_distribution=signals,
        recent_agents=recent_agents,
        recent_retrievals=recent_retrievals,
        recent_alerts=recent_alerts,
        recent_tasks=recent_tasks,
        latest_context=latest_context,
        generated_at=as_of,
    )

    with _cache_lock:
        _set_cache(key, data)

    return data
