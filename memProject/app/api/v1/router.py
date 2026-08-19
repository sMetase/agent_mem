# -*- coding: utf-8 -*-
"""
API v1 路由聚合器 — 按模块注册子路由。

路由表：
  /api/v1/agent/*       — 智能体管理（Phase 1）
  /api/v1/scene/*       — 场景管理（Phase 1）
  /api/v1/session/*     — 会话管理（Phase 1）
  /api/v1/task/*        — 任务管理（Phase 1）
  /api/v1/memory/*      — 记忆核心 API（Phase 2-4）
  /api/v1/admin/*       — 管理后台（Phase 5）
"""

from fastapi import APIRouter

from app.api.v1 import agent, scene, session, task, memory, generation, admin, monitor, auth

api_router = APIRouter()

# 控制台用户登录（登录即注册）
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])

# Phase 1: 智能体接入 & 实体管理
api_router.include_router(agent.router, prefix="/agent", tags=["Agent"])
api_router.include_router(scene.router, prefix="/scene", tags=["Scene"])
api_router.include_router(session.router, prefix="/session", tags=["Session"])
api_router.include_router(task.router, prefix="/task", tags=["Task"])

# Phase 2-4: 记忆核心 API
api_router.include_router(memory.router, prefix="/memory", tags=["Memory"])
api_router.include_router(generation.router, prefix="/memory", tags=["Memory Generation"])

# Phase 5: 管理后台
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])

# 可观测（P1-监控）
api_router.include_router(monitor.router, prefix="/monitor", tags=["Monitor"])
