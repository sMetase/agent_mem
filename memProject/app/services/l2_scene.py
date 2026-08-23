# -*- coding: utf-8 -*-
"""
L2 场景聚合 — 把 L1 原子记忆按主题聚合成有叙事的场景块（折中版：单次 LLM 全文重写）。

设计（对应方案块 B）：
- 折中版：PG 表 t_scene_block 存叙事全文，单次 LLM 全文重写（保留深度整合）。
- 聚合粒度：(scene_id, user_id) 跨 agent。
- 策略：update（归入已有场景）/ create（新建场景）/ merge（合并多场景）。
- 场景名 scene_name 由 LLM 在 user 范围内自动命名。
"""

import math
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, delete

from app.core.logger import get_logger
from app.models.base import SceneBlock
from app.services.embedding_client import embedding_client
from app.services.llm_client import llm_client

logger = get_logger("l2_scene")

L2_SYSTEM_PROMPT = """你是记忆整合架构师。把零散的原子记忆（点）深度整合成有叙事、有上下文的场景块（线）。

场景块是围绕一个主题的连贯叙事（如"日本旅行"、"竞品分析"），把相关记忆**深度整合**进去——重写叙事、融入新信息、体现因果和上下文，而不是简单罗列事实。

策略（重要——优先 update，避免同一主题被拆成多个块）：
- 优先 update：只要新记忆能归入某个已有场景，就 update（深度整合进该场景，重写叙事）。scene_name 必须和已有场景名**完全一致**，不要为已有主题新命名。
- create：只有真正全新的主题（已有场景都不匹配）才 create 新建场景块。
- merge：新记忆把多个已有场景串起来了，合并成一个场景（merged_from 列出被合并的场景名）。

输出 JSON：
{"operations": [{"action": "update"/"create"/"merge", "scene_name": "主题名", "content": "整合后的叙事全文", "summary": "一句话摘要", "memory_ids": ["新归入的记忆id"], "merged_from": ["被合并的场景名"]}]}

注意：
- content 是深度整合后的完整叙事全文（不是摘要、不是追加）。
- 只有 merge 才需要 merged_from 字段。
- memory_ids 只列本次新归入的记忆 id。"""


def _gen_block_id() -> str:
    return f"sb_{uuid4().hex[:16]}"


# scene_name 未精确命中时，用 embedding 余弦相似度判定「归入已有块 vs 新建块」的阈值。
# 值偏保守（0.75）：宁可多归并、不误拆主题，避免 LLM 对同一主题措辞微变导致重复建块。
SCENE_MATCH_THRESHOLD = 0.75


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度（BGE-M3 向量已归一化，等价于点积）。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _scene_embed_text(scene_name: str, content: str) -> str:
    """生成用于 embedding 匹配的文本（scene_name + content 前缀）。"""
    return f"{scene_name}: {(content or '')[:200]}"


async def aggregate_scenes(
    user_id: str,
    scene_id: str,
    new_memories: list[dict],
    existing_blocks: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """把新 L1 记忆聚合到场景块，返回 operations 列表（不落库）。"""
    if not new_memories:
        return []

    mem_lines = "\n".join(
        f"- [{m['memory_id']}] ({m.get('memory_type', 'fact')}) {m['content']}"
        for m in new_memories
    )
    block_lines = "\n\n".join(
        f"## 场景「{b['scene_name']}」\n{b['content']}"
        for b in existing_blocks
    ) or "（无已有场景块）"

    user_content = (
        f"## 新记忆\n{mem_lines}\n\n## 已有场景块\n{block_lines}"
    )

    try:
        result = await llm_client.extract_structured(
            system_prompt=L2_SYSTEM_PROMPT,
            user_content=user_content,
            output_schema={"type": "object"},
            max_tokens=3000,
            model=model,
            api_key=api_key,
        )
    except Exception as e:
        logger.error(f"L2 聚合 LLM 失败: user={user_id}, scene={scene_id}, error={e}")
        return []

    operations = result.get("operations", []) if isinstance(result, dict) else []
    if not isinstance(operations, list):
        logger.warning(f"L2 聚合返回非法 operations: {type(operations)}")
        return []
    return operations


async def apply_scene_operations(
    db,
    user_id: str,
    scene_id: str,
    operations: list[dict],
) -> None:
    """应用 L2 聚合结果落库（update/create/merge）。scene_name 先精确匹配，未命中时用 embedding 相似度判定。"""
    if not operations:
        return

    result = await db.execute(
        select(SceneBlock).where(SceneBlock.user_id == user_id, SceneBlock.scene_id == scene_id)
    )
    existing_blocks = list(result.scalars().all())
    blocks_by_name = {b.scene_name: b for b in existing_blocks}

    # 惰性缓存已有块的 embedding（仅当需要近似匹配时计算，避免每轮都调 embedding）
    block_embeddings: dict[str, list[float]] | None = None

    async def _load_block_embeddings() -> dict[str, list[float]]:
        nonlocal block_embeddings
        if block_embeddings is not None:
            return block_embeddings
        block_embeddings = {}
        if not existing_blocks:
            return block_embeddings
        try:
            texts = [_scene_embed_text(b.scene_name, b.content or "") for b in existing_blocks]
            vecs = await embedding_client.embed_batch(texts)
            block_embeddings = {b.scene_block_id: v for b, v in zip(existing_blocks, vecs)}
        except Exception as e:
            logger.warning(f"L2 已有块 embedding 失败，近似匹配降级为精确匹配: {e}")
            block_embeddings = {}
        return block_embeddings

    for op in operations:
        action = op.get("action", "create")
        scene_name = (op.get("scene_name") or "").strip()
        content = (op.get("content") or "").strip()
        summary = (op.get("summary") or "").strip()
        memory_ids = op.get("memory_ids") or []

        if not scene_name or not content:
            continue

        block = blocks_by_name.get(scene_name)
        if block is None and existing_blocks:
            # 字符串未命中 → embedding 近似匹配（LLM 对同一主题措辞可能微变）
            emb_map = await _load_block_embeddings()
            if emb_map:
                try:
                    query_vec = await embedding_client.embed_single(
                        _scene_embed_text(scene_name, content)
                    )
                    best_block, best_score = None, 0.0
                    for b in existing_blocks:
                        bv = emb_map.get(b.scene_block_id)
                        if bv is None:
                            continue
                        s = _cosine_similarity(query_vec, bv)
                        if s > best_score:
                            best_score, best_block = s, b
                    if best_block is not None and best_score >= SCENE_MATCH_THRESHOLD:
                        logger.info(
                            f"L2 scene_name 近似归入: '{scene_name}' → '{best_block.scene_name}' "
                            f"(sim={best_score:.3f})"
                        )
                        block = best_block
                        scene_name = best_block.scene_name  # 统一用已有块名，保持命名稳定
                except Exception as e:
                    logger.warning(f"L2 embedding 匹配失败，回退 create: {e}")

        if block is None:
            # create（或 merge 后新场景名不存在）
            block = SceneBlock(
                scene_block_id=_gen_block_id(),
                user_id=user_id,
                scene_id=scene_id,
                scene_name=scene_name,
                content=content,
                summary=summary,
                memory_ids=memory_ids,
                heat=1,
            )
            db.add(block)
            blocks_by_name[scene_name] = block
        else:
            # update：重写叙事 + 合并 memory_ids + 热度+1
            block.content = content
            block.summary = summary
            block.memory_ids = list(set(block.memory_ids or []) | set(memory_ids))
            block.heat = (block.heat or 0) + 1

        # merge：删除被合并的旧场景块
        if action == "merge":
            for merged_name in (op.get("merged_from") or []):
                mb = blocks_by_name.get(merged_name)
                if mb is not None and mb.scene_block_id != block.scene_block_id:
                    await db.execute(
                        delete(SceneBlock).where(SceneBlock.scene_block_id == mb.scene_block_id)
                    )
                    del blocks_by_name[merged_name]

    await db.commit()
    logger.info(
        f"L2 场景落库完成: user={user_id}, scene={scene_id}, operations={len(operations)}"
    )


async def get_scene_navigation(db, user_id: str, scene_id: str) -> list[dict]:
    """场景导航：所有场景块的 (scene_name, summary, heat)，按 heat 降序（实时派生，不单独存）。"""
    result = await db.execute(
        select(SceneBlock)
        .where(
            SceneBlock.user_id == user_id,
            SceneBlock.scene_id == scene_id,
            SceneBlock.status == "active",
        )
        .order_by(SceneBlock.heat.desc())
    )
    return [
        {
            "scene_name": b.scene_name,
            "summary": b.summary or "",
            "heat": b.heat or 0,
        }
        for b in result.scalars().all()
    ]
