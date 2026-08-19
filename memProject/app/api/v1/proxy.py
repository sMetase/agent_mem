# -*- coding: utf-8 -*-
"""
透明代理（Proxy）— 接收外部 Agent 的 LLM 请求，召回注入 + 转发 + 异步写回。

设计（对应方案工作流 2 / P0）：
- 挂现有 FastAPI（Q9）。
- spaceId 从 URL 提取，映射到 {user_id, api_key, scene_id, agent_id}（YAML 配置）。
- sessionKey 从 header 提取（6 候选名 + fallback spaceId），映射到 session_id（内存 dict）。
- 召回注入：可插拔注入器，返回 {target: "user"/"system", content}（Q6）。
- 转发：复用 DEEPSEEK 配置（Q2），透传 model。
- 写回：异步（后台任务），写本轮对话。
- 鉴权：内网不加额外鉴权（spaceId 即身份），公网留 proxy key 钩子（默认关闭，Q5）。
"""

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("proxy")

router = APIRouter()

settings = get_settings()
MEMORY_BASE_URL = f"http://127.0.0.1:{settings.server.port}"

# sessionKey 候选 header 名（对应 TencentDB resolveConversationId）
SESSION_HEADER_NAMES = [
    "x-conversation-id", "x-session-id", "x-claude-code-session-id",
    "x-deepseek-harness-session-id", "x-chat-id", "x-thread-id",
]

# 共享 httpx 客户端（复用连接池）
_http_client: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _http_client


def _load_spaces() -> dict:
    path = Path(__file__).resolve().parents[3] / "spaces.yaml"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("spaces", {})
    return {}


SPACES = _load_spaces()


def _extract_session_key(request: Request, space_id: str) -> str:
    for name in SESSION_HEADER_NAMES:
        val = request.headers.get(name)
        if val:
            return val
    return space_id  # fallback：spaceId 兜底


def _extract_last_user_message(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _space_headers(space: dict, with_user: bool = False) -> dict:
    h = {
        "X-API-Key": space["api_key"],
        "X-Agent-Id": space["agent_id"],
        "Content-Type": "application/json",
    }
    if with_user:
        h["X-User-Id"] = space["user_id"]
    return h


# ============================================================
# 会话管理
# ============================================================

async def _create_session(space: dict) -> str:
    body = {"user_id": space["user_id"], "scene_id": space["scene_id"]}
    r = await _get_http().post(
        f"{MEMORY_BASE_URL}/api/v1/session",
        json=body, headers=_space_headers(space),
    )
    r.raise_for_status()
    return r.json()["data"]["session_id"]


async def _get_or_create_session(space_id: str, session_key: str, space: dict) -> str:
    """获取或创建 session（sessionKey → session_id 映射，落 DB 避免重启记忆分家）。

    并发 get-or-create 竞争：先查后建 + commit 冲突时读回已有映射（方案 2）。
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.core.database import async_session_factory
    from app.models.base import ProxySession

    async with async_session_factory() as db:
        result = await db.execute(
            select(ProxySession).where(
                ProxySession.space_id == space_id,
                ProxySession.session_key == session_key,
            )
        )
        ps = result.scalar_one_or_none()
        if ps:
            return ps.session_id

        session_id = await _create_session(space)
        db.add(ProxySession(space_id=space_id, session_key=session_key, session_id=session_id))
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if "23505" in str(e.orig):  # 唯一约束违反（并发竞争），读回已有映射
                existing = (
                    await db.execute(
                        select(ProxySession).where(
                            ProxySession.space_id == space_id,
                            ProxySession.session_key == session_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    logger.info(f"并发竞争命中已有会话: space={space_id}, session_key={session_key}, session_id={existing.session_id}")
                    return existing.session_id
            raise  # 其他 IntegrityError 是真错误，不掩盖
        logger.info(f"新建会话: space={space_id}, session_key={session_key}, session_id={session_id}")
        return session_id


# ============================================================
# 可插拔注入器（Q6：返回 {target: "user"/"system", content}）
# ============================================================

class L1MemoryInjector:
    """L1 召回注入器：调 /memory/context，注入 user prompt（动态）。"""
    name = "l1_memory"

    async def inject(self, query: str, space: dict) -> dict:
        body = {
            "query": query,
            "user_id": space["user_id"],
            "memory_types": ["preference", "fact"],
            "top_k": 5,
            "max_tokens": 2000,
        }
        r = await _get_http().post(
            f"{MEMORY_BASE_URL}/api/v1/memory/context",
            json=body, headers=_space_headers(space, with_user=True),
        )
        r.raise_for_status()
        formatted_text = r.json().get("data", {}).get("formatted_text", "")
        return {"target": "user", "content": formatted_text}


INJECTORS = [L1MemoryInjector()]


async def _run_injectors(query: str, space: dict) -> tuple[str, str]:
    """执行所有注入器，返回 (user_text, system_text)。"""
    user_parts, system_parts = [], []
    for inj in INJECTORS:
        try:
            result = await inj.inject(query, space)
            content = (result.get("content") or "").strip()
            if not content:
                continue
            if result.get("target") == "system":
                system_parts.append(content)
            else:
                user_parts.append(content)
        except Exception as e:
            logger.warning(f"注入器 {getattr(inj, 'name', str(inj))} 失败: {e}")
    return "\n\n".join(user_parts), "\n\n".join(system_parts)


# ============================================================
# LLM 转发（复用 DEEPSEEK 配置，透传 model）
# ============================================================

async def _forward_llm(messages: list, model: str) -> str:
    from app.services.llm_client import llm_client as _llm
    payload = {
        "model": model or _llm._model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    r = await _llm.http.post(f"{_llm._base_url}/chat/completions", json=payload)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


# ============================================================
# 异步写回
# ============================================================

async def _write_back(space: dict, session_id: str, user_msg: str, reply: str) -> None:
    body = {
        "user_id": space["user_id"],
        "scene_id": space["scene_id"],
        "session_id": session_id,
        "interaction_type": "dialogue",
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": reply},
        ],
    }
    try:
        await _get_http().post(
            f"{MEMORY_BASE_URL}/api/v1/memory/write",
            json=body, headers=_space_headers(space, with_user=True),
        )
    except Exception as e:
        logger.error(f"写回失败: space={space.get('scene_id')}, error={e}")


# ============================================================
# 端点
# ============================================================

@router.post("/proxy/{space_id}/v1/chat/completions")
async def proxy_chat_completion(space_id: str, request: Request):
    """OpenAI 兼容透明代理端点。"""
    space = SPACES.get(space_id)
    if not space:
        return JSONResponse(status_code=404, content={"error": {"message": f"未知 spaceId: {space_id}"}})

    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", "")

    session_key = _extract_session_key(request, space_id)
    session_id = await _get_or_create_session(space_id, session_key, space)

    query = _extract_last_user_message(messages)
    user_text, system_text = await _run_injectors(query, space)

    # 注入：system 注入尾部 / user 注入当前用户消息前缀
    injected_messages = list(messages)
    if system_text:
        injected_messages.insert(0, {"role": "system", "content": system_text})
    if user_text:
        for i in range(len(injected_messages) - 1, -1, -1):
            if injected_messages[i].get("role") == "user":
                original = injected_messages[i].get("content", "")
                injected_messages[i]["content"] = f"{user_text}\n\n{original}"
                break

    try:
        reply = await _forward_llm(injected_messages, model)
    except Exception as e:
        logger.error(f"LLM 转发失败: {e}")
        return JSONResponse(status_code=502, content={"error": {"message": f"上游 LLM 转发失败: {e}"}})

    asyncio.create_task(_write_back(space, session_id, query, reply))

    return {
        "id": f"chatcmpl-{uuid4().hex[:16]}",
        "object": "chat.completion",
        "model": model or "deepseek-chat",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
