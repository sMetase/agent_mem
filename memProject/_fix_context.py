with open('app/api/v1/memory.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_sig = '@router.post("/context", summary="Prompt'
old_start = content.find(old_sig)
if old_start < 0:
    raise SystemExit("Context function not found")

# Find the closing paren of the error return
end_marker = 'error_code="CONTEXT_FAILED",\n        )'
end_idx = content.find(end_marker, old_start)
if end_idx < 0:
    raise SystemExit("End of context function not found")
end_idx = content.index(')', end_idx + len(end_marker))
old_block = content[old_start:end_idx + 1]

new_block = r'''# Context assembly helpers
GROUP_TITLES = {
    "preference": "## User Preferences",
    "fact": "## Key Facts",
    "task_state": "## Task State",
    "process": "## Process Experience",
}
TYPE_PRIORITY = {"preference": 1, "fact": 2, "task_state": 3, "process": 4}
CONTENT_MAX_LEN = 200
SCORE_MIN_THRESHOLD = 0.5
MAX_MEMORY_COUNT = 10


@router.post("/context", summary="Prompt context fragment")
async def memory_context(
    body: ContextRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """Prompt context: search -> group by type -> assemble within capacity budget."""
    try:
        from app.core.qdrant_client import qdrant_client as _qd
        from app.services.embedding_client import embedding_client as _emb
        from app.models.base import MemoryVector, Memory
        from sqlalchemy import select as _sel
        import math as _math

        # Step 1: Search
        query_vector = await _emb.embed_single(body.query)
        payload_filters = {}
        if body.scene_id:
            payload_filters["scene_id"] = body.scene_id
        if body.task_id:
            payload_filters["task_id"] = body.task_id
        if body.session_id:
            payload_filters["session_id"] = body.session_id

        top_k = body.top_k or 10
        hits = _qd.search_similar(
            query_vector=query_vector,
            user_id=body.user_id,
            top_k=max(top_k * 3, 30),
            payload_filters=payload_filters if payload_filters else None,
        )
        if not hits:
            return ok({"formatted_text": "", "memory_count": 0, "estimated_tokens": 0})

        # Step 2: T_MEMORY_VECTOR bridge -> T_MEMORY
        point_scores = {str(h["id"]): float(h["score"]) if h["score"] is not None else 0.0 for h in hits}
        mv_result = await db.execute(
            _sel(MemoryVector).where(MemoryVector.vector_store_id.in_(list(point_scores.keys())))
        )
        id_map = {}
        for mv in mv_result.scalars().all():
            id_map[mv.memory_id] = point_scores.get(mv.vector_store_id, 0.0)
        if not id_map:
            return ok({"formatted_text": "", "memory_count": 0, "estimated_tokens": 0})

        mem_query = _sel(Memory).where(Memory.memory_id.in_(list(id_map.keys())))
        if body.memory_types:
            mem_query = mem_query.where(Memory.memory_type.in_(body.memory_types))
        if body.status:
            mem_query = mem_query.where(Memory.status.in_(body.status))
        else:
            mem_query = mem_query.where(Memory.status == "active")
        mem_result = await db.execute(mem_query)
        db_memories = {m.memory_id: m for m in mem_result.scalars().all()}

        # Step 3: Re-rank + filter
        now_dt = datetime.now(timezone.utc)
        HALF_LIFE_DAYS = 30
        scored = []
        for memory_id, mem_score in id_map.items():
            mem = db_memories.get(memory_id)
            if not mem:
                continue
            ms = mem_score or 0
            recency_val = 0.5
            if mem.created_at:
                try:
                    cd = mem.created_at.replace(tzinfo=None) if mem.created_at.tzinfo else mem.created_at
                    age_seconds = max(0, (now_dt.replace(tzinfo=None) - cd).total_seconds())
                    age_days = age_seconds / 86400
                    recency_val = _math.pow(0.5, age_days / HALF_LIFE_DAYS)
                except Exception:
                    pass
            final_score = round(
                (ms or 0) * 0.6 + recency_val * 0.15
                + (mem.importance or 0.5) * 0.15 + (mem.confidence or 0.5) * 0.1, 4
            )
            if final_score < SCORE_MIN_THRESHOLD:
                continue
            scored.append({
                "content": mem.content or "",
                "summary": mem.summary or "",
                "memory_type": mem.memory_type or "fact",
                "relevance_score": final_score,
            })
        if not scored:
            return ok({"formatted_text": "", "memory_count": 0, "estimated_tokens": 0})

        # Step 4: Group by type + sort
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        groups = {}
        for item in scored:
            mt = item["memory_type"]
            if mt == "correction":
                continue
            groups.setdefault(mt, []).append(item)
        sorted_types = sorted(
            [t for t in groups if t in TYPE_PRIORITY],
            key=lambda t: TYPE_PRIORITY[t],
        )

        # Step 5: Assemble within budget
        max_tokens = body.max_tokens or 3000
        lines = []
        token_estimate = 0
        memory_count = 0
        for mt in sorted_types:
            if memory_count >= MAX_MEMORY_COUNT:
                break
            title = GROUP_TITLES.get(mt, f"## {mt}")
            lines.append(title)
            token_estimate += len(title) // 2
            for item in groups[mt]:
                if memory_count >= MAX_MEMORY_COUNT:
                    break
                text = item["content"]
                if len(text) > CONTENT_MAX_LEN and item["summary"]:
                    text = item["summary"]
                line = f"- {text}"
                est = len(line) // 2
                if token_estimate + est > max_tokens:
                    break
                lines.append(line)
                token_estimate += est
                memory_count += 1
            if token_estimate >= max_tokens:
                break

        formatted_text = "\n".join(lines) if lines else ""
        return ok({"formatted_text": formatted_text, "memory_count": memory_count, "estimated_tokens": token_estimate})

    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        return error(
            message="Context generation failed",
            code=-2,
            data={"formatted_text": "", "memory_count": 0, "estimated_tokens": 0},
            error_code="CONTEXT_FAILED",
        )'''

new_content = content[:old_start] + new_block + content[end_idx + 1:]
with open('app/api/v1/memory.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Done')
