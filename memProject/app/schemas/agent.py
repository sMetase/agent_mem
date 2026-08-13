# -*- coding: utf-8 -*-
"""
智能体相关 Schema。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentRegisterRequest(BaseModel):
    """智能体注册请求"""
    agent_name: str = Field(..., min_length=1, max_length=256, description="智能体名称")
    scene_id: str = Field(..., min_length=1, max_length=128, description="所属场景标识（必填，用于数据隔离）")
    permissions: Optional[list[str]] = Field(default=["read", "write"], description="权限列表")


class AgentRegisterResponse(BaseModel):
    """注册响应 — 返回 API Key（仅此一次）"""
    agent_id: str = Field(..., description="智能体唯一标识")
    agent_name: str
    api_key: str = Field(..., description="API Key 明文，仅此次返回，请妥善保存")
    api_key_prefix: str = Field(..., description="API Key 前缀，用于展示")
    created_at: datetime


class AgentUpdateRequest(BaseModel):
    """智能体更新请求"""
    agent_name: Optional[str] = Field(None, max_length=256)
    is_active: Optional[bool] = Field(None, description="启用/停用")
    permissions: Optional[list[str]] = Field(None)
    extra_meta: Optional[dict[str, Any]] = Field(None)


class AgentInfo(BaseModel):
    """智能体信息（不含敏感字段）"""
    agent_id: str
    agent_name: str
    scene_id: Optional[str] = None
    api_key_prefix: Optional[str] = None
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentListResponse(BaseModel):
    """智能体列表"""
    items: list[AgentInfo]
    total: int


class ApiKeyRotateResponse(BaseModel):
    """API Key 轮换响应"""
    agent_id: str
    api_key: str = Field(..., description="新的 API Key 明文")
    api_key_prefix: str
