# -*- coding: utf-8 -*-
"""
L3 画像生成 — 从 L2 场景块抽象出长期稳定画像（persona 自由文本）。

设计（对应方案块 C）：
- C2 增量：只读「变化场景」（updated_at > last_persona_time），first 模式全量，无变化跳过。
- 形态复用块 B 折中版（单次 LLM + PG 表 t_persona 存自由文本）。
- 聚合粒度 (scene_id, user_id) 跨 agent。
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func

from app.core.logger import get_logger
from app.models.base import Memory, Persona, SceneBlock
from app.services.llm_client import llm_client
from app.services.llm_config import resolve_llm_config

logger = get_logger("l3_persona")

L3_SYSTEM_PROMPT = """你是画像架构师（Persona Architect）。从场景块的叙事中，提炼用户跨场景、跨会话的稳定特征。

要求：
- 挑最重要的 3-5 条特质，每条一句话，要点式输出（不要长段落）。
- 只基于场景块有证据的信息，不臆测。
- 全文 300 字以内，中文。

直接输出要点，不要 JSON。"""


def _gen_persona_id() -> str:
    return f"persona_{uuid4().hex[:16]}"


async def generate_persona(db, user_id: str, scene_id: str) -> dict:
    """从 L2 场景块生成/更新 L3 画像。只读变化场景，无变化跳过。"""
    result = await db.execute(
        select(Persona).where(Persona.user_id == user_id, Persona.scene_id == scene_id)
    )
    persona = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    last_time = persona.last_persona_time if persona else None

    # 读变化场景（updated_at > last_time；first 模式即 last_time=None 时全量）
    stmt = select(SceneBlock).where(
        SceneBlock.user_id == user_id,
        SceneBlock.scene_id == scene_id,
        SceneBlock.status == "active",
    )
    if last_time:
        stmt = stmt.where(SceneBlock.updated_at > last_time)
    result = await db.execute(stmt.order_by(SceneBlock.heat.desc()))
    changed_scenes = list(result.scalars().all())

    if not changed_scenes:
        if persona:
            return {"persona_id": persona.persona_id, "skipped": True, "content": persona.content}
        return {"skipped": True}

    scene_lines = "\n\n".join(f"## 场景「{s.scene_name}」\n{s.content}" for s in changed_scenes)
    existing_persona = persona.content if persona else "（无已有画像，首次生成）"

    user_content = f"## 已有画像\n{existing_persona}\n\n## 变化场景\n{scene_lines}"

    try:
        model, api_key = await resolve_llm_config(db, agent_id=None)
        content = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": L3_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2000,
            model=model,
            api_key=api_key,
        )
    except Exception as e:
        logger.error(f"L3 画像生成失败: user={user_id}, scene={scene_id}, error={e}")
        return {"skipped": True, "error": str(e)}

    content = (content or "").strip()
    if not content:
        return {"skipped": True}

    # 更新 last_seq_id（当前 max L1 seq_id，C1 触发计数用）
    max_seq = await db.execute(
        select(func.max(Memory.seq_id)).where(
            Memory.user_id == user_id, Memory.scene_id == scene_id
        )
    )
    last_seq_id = max_seq.scalar() or 0

    # upsert：唯一约束 + ON CONFLICT DO UPDATE，并发安全，避免重复 persona
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(Persona).values(
        persona_id=_gen_persona_id(),
        user_id=user_id,
        scene_id=scene_id,
        content=content,
        last_persona_time=now,
        last_seq_id=last_seq_id,
    ).on_conflict_do_update(
        index_elements=["user_id", "scene_id"],
        set_={
            "content": content,
            "last_persona_time": now,
            "last_seq_id": last_seq_id,
        },
    )
    await db.execute(stmt)
    await db.commit()

    # 回查 persona_id（insert 用新 id，update 保持原 id）
    result = await db.execute(
        select(Persona.persona_id).where(
            Persona.user_id == user_id, Persona.scene_id == scene_id
        )
    )
    persona_id = result.scalar_one_or_none()

    logger.info(
        f"L3 画像生成完成: user={user_id}, scene={scene_id}, changed_scenes={len(changed_scenes)}"
    )
    return {"persona_id": persona_id or "", "content": content, "changed_scenes": len(changed_scenes)}
