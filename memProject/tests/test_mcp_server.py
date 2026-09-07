"""Tests for the embedded memProject MCP server."""

import asyncio

import httpx

from app import mcp_server


EXPECTED_TOOLS = {
    "create_session",
    "write_conversation",
    "write_session_summary",
    "search_memories",
    "get_memory_context",
    "close_session",
}


def test_mcp_tools_are_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_backend_mounts_mcp_endpoint():
    from app.main import app

    mounted_paths = {
        route.path for route in app.routes if getattr(route, "path", None)
    }
    assert "/mcp" in mounted_paths


def test_mcp_endpoint_is_reachable_from_backend_asgi_app():
    from app.main import app

    async def request_mcp_endpoint():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            return await client.get("/mcp")

    response = asyncio.run(request_mcp_endpoint())

    # Streamable HTTP accepts POST/DELETE; GET must be handled by the mounted route,



    
    # rather than falling through to the backend's 404 handler.
    assert response.status_code == 405


def test_write_conversation_maps_to_memory_write(monkeypatch):
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured.update(method=method, path=path, kwargs=kwargs)
        return {"accepted": True}

    monkeypatch.setattr(mcp_server, "_request", fake_request)

    result = asyncio.run(
        mcp_server.write_conversation(
            user_id="user_001",
            session_id="session_001",
            messages=[{"role": "user", "content": "我喜欢 Python"}],
            scene_id="scene_001",
            agent_id="agent_001",
        )
    )

    assert result == {"accepted": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/memory/write"
    assert captured["kwargs"]["user_id"] == "user_001"
    assert captured["kwargs"]["agent_id"] == "agent_001"
    assert captured["kwargs"]["json"] == {
        "user_id": "user_001",
        "session_id": "session_001",
        "scene_id": "scene_001",
        "interaction_type": "dialogue",
        "messages": [{"role": "user", "content": "我喜欢 Python"}],
    }


def test_search_memories_maps_filters(monkeypatch):
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured.update(method=method, path=path, kwargs=kwargs)
        return {"results": []}

    monkeypatch.setattr(mcp_server, "_request", fake_request)

    result = asyncio.run(
        mcp_server.search_memories(
            user_id="user_001",
            query="用户偏好",
            session_id="session_001",
            scene_id="scene_001",
            top_k=5,
            agent_id="agent_001",
        )
    )

    assert result == {"results": []}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/memory/search"
    assert captured["kwargs"]["json"]["top_k"] == 5
    assert captured["kwargs"]["json"]["session_id"] == "session_001"
    assert captured["kwargs"]["json"]["agent_id"] == "agent_001"
