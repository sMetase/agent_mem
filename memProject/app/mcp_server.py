"""memProject MCP Server.

The MCP surface is an adapter over the memProject REST API. OpenMemory remains
an internal backend storage dependency and is not exposed by this process.
"""

import asyncio
import os
from typing import Any

import httpx
from fastmcp import FastMCP

REST_BASE_URL = os.getenv("MEMPROJECT_API_URL", "http://127.0.0.1:8000").rstrip("/")
MCP_HOST = os.getenv("MEMPROJECT_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MEMPROJECT_MCP_PORT", "8001"))
MCP_API_KEY = os.getenv("MEMPROJECT_MCP_API_KEY", "")

mcp = FastMCP(
    "memProject Memory Server",
    instructions=(
        "Use write_conversation to store conversation turns, search_memories "
        "to retrieve memories, and get_memory_context to assemble context for a reply. "
        "This server uses the memProject API and its configured storage pipeline. "
        "OpenMemory is internal and is not exposed as a public MCP endpoint."
    ),
)


async def _request(
    method: str,
    path: str,
    *,
    user_id: str,
    agent_id: str | None = None,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    headers = {
        "X-User-Id": user_id,
        "X-Agent-Id": agent_id or "agent_mcp",
    }
    if MCP_API_KEY:
        headers["X-API-Key"] = MCP_API_KEY

    async with httpx.AsyncClient(base_url=REST_BASE_URL, timeout=60.0) as client:
        response = await client.request(
            method,
            path,
            headers=headers,
            json=json,
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

    if payload.get("code", 0) != 0:
        raise RuntimeError(payload.get("message", "memProject API request failed"))
    return payload.get("data")


@mcp.tool()
async def create_session(
    user_id: str,
    scene_id: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create an active conversation session in memProject."""
    return await _request(
        "POST",
        "/api/v1/session",
        user_id=user_id,
        agent_id=agent_id,
        json={
            "user_id": user_id,
            "scene_id": scene_id,
            "agent_id": agent_id,
            "task_id": task_id,
        },
    )


@mcp.tool()
async def write_conversation(
    user_id: str,
    session_id: str,
    messages: list[dict[str, str]],
    scene_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Write conversation messages for asynchronous memory extraction."""
    return await _request(
        "POST",
        "/api/v1/memory/write",
        user_id=user_id,
        agent_id=agent_id,
        json={
            "user_id": user_id,
            "session_id": session_id,
            "scene_id": scene_id,
            "interaction_type": "dialogue",
            "messages": messages,
        },
    )


@mcp.tool()
async def write_session_summary(
    user_id: str,
    session_id: str,
    session_summary: str,
    session_time: str | None = None,
    session_source: str | None = None,
    scene_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Write a historical session summary for asynchronous memory extraction."""
    return await _request(
        "POST",
        "/api/v1/memory/write",
        user_id=user_id,
        agent_id=agent_id,
        json={
            "user_id": user_id,
            "session_id": session_id,
            "scene_id": scene_id,
            "interaction_type": "session",
            "session_summary": session_summary,
            "session_time": session_time,
            "session_source": session_source,
        },
    )


@mcp.tool()
async def search_memories(
    user_id: str,
    query: str,
    session_id: str | None = None,
    scene_id: str | None = None,
    top_k: int = 10,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Search memProject memories with hybrid semantic retrieval."""
    return await _request(
        "POST",
        "/api/v1/memory/search",
        user_id=user_id,
        agent_id=agent_id,
        json={
            "user_id": user_id,
            "query": query,
            "session_id": session_id,
            "scene_id": scene_id,
            "top_k": top_k,
            "agent_id": agent_id,
        },
    )


@mcp.tool()
async def get_memory_context(
    user_id: str,
    query: str,
    session_id: str | None = None,
    scene_id: str | None = None,
    max_tokens: int = 3000,
    top_k: int = 10,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Assemble retrieved memories into a prompt-ready context fragment."""
    return await _request(
        "POST",
        "/api/v1/memory/context",
        user_id=user_id,
        agent_id=agent_id,
        json={
            "user_id": user_id,
            "query": query,
            "session_id": session_id,
            "scene_id": scene_id,
            "max_tokens": max_tokens,
            "top_k": top_k,
            "agent_id": agent_id,
        },
    )


@mcp.tool()
async def close_session(
    user_id: str,
    session_id: str,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Close a session and trigger its configured memory compression flow."""
    return await _request(
        "POST",
        f"/api/v1/session/{session_id}/close",
        user_id=user_id,
        agent_id=agent_id,
    )


async def main() -> None:
    print(f"memProject MCP Server listening on http://{MCP_HOST}:{MCP_PORT}/mcp", flush=True)
    await mcp.run_http_async(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path="/mcp",
        stateless_http=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
