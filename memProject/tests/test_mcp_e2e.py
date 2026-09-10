"""End-to-end test for the running memProject MCP HTTP server.

Run with:
    pytest -q tests/test_mcp_e2e.py -s

The test skips when the backend is not running. It performs real writes and
retrievals, so it requires PostgreSQL, Qdrant, the backend, and valid model
provider credentials.
"""

import asyncio
import json
import os
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client


MCP_URL = os.getenv("MEMPROJECT_MCP_TEST_URL", "http://localhost:8000/mcp/")
USER_ID = os.getenv("MEMPROJECT_MCP_TEST_USER", f"mcp_test_{uuid4().hex[:8]}")
AGENT_ID = os.getenv("MEMPROJECT_MCP_TEST_AGENT", "agent_dev_default")
SCENE_ID = os.getenv("MEMPROJECT_MCP_TEST_SCENE", "mcp_test_scene")
WAIT_TIMEOUT_SECONDS = float(os.getenv("MEMPROJECT_MCP_TEST_TIMEOUT", "90"))
POLL_INTERVAL_SECONDS = float(os.getenv("MEMPROJECT_MCP_TEST_INTERVAL", "5"))

EXPECTED_TOOLS = {
    "create_session",
    "write_conversation",
    "write_session_summary",
    "search_memories",
    "get_memory_context",
    "close_session",
}


async def _backend_is_available() -> bool:
    health_url = MCP_URL.removesuffix("/mcp/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(health_url)
        return response.is_success
    except httpx.HTTPError:
        return False


def _tool_data(result):
    """Return the structured payload across FastMCP result versions."""
    data = getattr(result, "data", None)
    if data is not None:
        return data

    content = getattr(result, "content", None) or []
    if len(content) == 1 and hasattr(content[0], "text"):
        import json

        return json.loads(content[0].text)
    return result


async def _wait_for_memory(
    client: Client, query: str, expected_text: str | None = None
) -> dict:
    deadline = asyncio.get_running_loop().time() + WAIT_TIMEOUT_SECONDS
    last_result = None

    while asyncio.get_running_loop().time() < deadline:
        result = await client.call_tool(
            "search_memories",
            {
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "scene_id": SCENE_ID,
                "query": query,
                "top_k": 10,
            },
        )
        last_result = _tool_data(result)
        result_text = json.dumps(last_result, ensure_ascii=False)
        if last_result.get("results") and (
            expected_text is None or expected_text in result_text
        ):
            return last_result
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    pytest.fail(
        f"在 {WAIT_TIMEOUT_SECONDS:g} 秒内没有召回新记忆；最后结果: {last_result}"
    )


@pytest.mark.asyncio
async def test_mcp_memory_write_and_retrieval_e2e():
    """Exercise the real MCP write -> async worker -> retrieval flow."""
    if not await _backend_is_available():
        pytest.skip(f"MCP backend 不可用: {MCP_URL}")

    async with Client(MCP_URL) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert EXPECTED_TOOLS <= tool_names

        # Seed two prior sessions through the public MCP API. This exercises
        # historical-session ingestion before testing retrieval.
        historical_sessions = [
            (
                "2026-09-01T10:00:00+08:00",
                "用户确定后端数据库使用 PostgreSQL，向量检索使用 Qdrant。",
            ),
            (
                "2026-09-05T15:30:00+08:00",
                "用户偏好简洁的中文回答，代码示例主要使用 Python。",
            ),
        ]
        for session_time, session_summary in historical_sessions:
            history_session_result = await client.call_tool(
                "create_session",
                {
                    "user_id": USER_ID,
                    "agent_id": AGENT_ID,
                    "scene_id": SCENE_ID,
                },
            )
            history_session_id = _tool_data(history_session_result)["session_id"]
            history_write_result = await client.call_tool(
                "write_session_summary",
                {
                    "user_id": USER_ID,
                    "agent_id": AGENT_ID,
                    "scene_id": SCENE_ID,
                    "session_id": history_session_id,
                    "session_summary": session_summary,
                    "session_time": session_time,
                    "session_source": "mcp_e2e_history_seed",
                },
            )
            assert _tool_data(history_write_result)["accepted"] is True

        historical_search_data = await _wait_for_memory(
            client,
            "用户之前确定的数据库和向量检索方案是什么？",
            expected_text="PostgreSQL",
        )
        assert historical_search_data["results"]

        session_result = await client.call_tool(
            "create_session",
            {
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "scene_id": SCENE_ID,
            },
        )
        session_data = _tool_data(session_result)
        session_id = session_data["session_id"]

        write_result = await client.call_tool(
            "write_conversation",
            {
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "scene_id": SCENE_ID,
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "我喜欢简洁的回答，并且主要使用 Python 开发。",
                    },
                    {
                        "role": "assistant",
                        "content": "好的，我会优先给出简洁的 Python 示例。",
                    },
                ],
            },
        )
        write_data = _tool_data(write_result)
        assert write_data["accepted"] is True

        search_data = await _wait_for_memory(
            client,
            "用户有什么回答偏好？",
            expected_text="Python",
        )
        assert search_data["results"]

        context_result = await client.call_tool(
            "get_memory_context",
            {
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "scene_id": SCENE_ID,
                "query": "请按照用户偏好回答问题",
                "top_k": 10,
                "max_tokens": 3000,
            },
        )
        context_data = _tool_data(context_result)
        assert context_data["memory_count"] > 0
        assert context_data["formatted_text"].strip()

        close_result = await client.call_tool(
            "close_session",
            {
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "session_id": session_id,
            },
        )
        close_data = _tool_data(close_result)
        assert close_data
