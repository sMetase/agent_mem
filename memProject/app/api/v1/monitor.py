# -*- coding: utf-8 -*-
"""
可观测端点 — worker 积压数 + 失败率 + 产出速率（P1-监控）。

只暴露聚合计数（不暴露记忆内容），供运维/监控用。
"""

from fastapi import APIRouter

from app.schemas.common import ok
from app.services.worker_stats import snapshot

router = APIRouter()


@router.get("/stats", summary="worker 可观测统计")
async def monitor_stats():
    return ok(await snapshot())
