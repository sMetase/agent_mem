# -*- coding: utf-8 -*-
"""
MCP Client — 连接 OpenMemory MCP Server（Streamable HTTP）。
支持本地开发模式和 Docker 容器模式。
"""

import json
import os
from typing import Optional

from fastmcp import Client

from app.core.logger import get_logger

logger = get_logger("mcp_client")

# OpenMemory MCP Server 地址
# 本地开发默认 http://localhost:8765/mcp
# Docker/Compose 默认可通过环境变量传入，例如 http://openmemory:8765/mcp
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8765/mcp")


class McpClient:
    """
    通过 Streamable HTTP 连接 OpenMemory MCP Server。
    每次请求动态构造带 user_id 的端点 URL。
    """

    def __init__(self, client_name: str = "memproject"):
        self.client_name = client_name
        # 按 user_id 缓存 Client 实例，避免每次请求都重新握手
        self._clients: dict[str, Client] = {}

    def _get_client(self, user_id: str) -> Client:
        if user_id not in self._clients:
            url = f"{MCP_BASE_URL}/{self.client_name}/http/{user_id}"
            self._clients[user_id] = Client(url)
            logger.info(f"MCP client created: {url}")
        return self._clients[user_id]

    async def close_user(self, user_id: str) -> None:
        if user_id in self._clients:
            await self._clients[user_id].close()
            del self._clients[user_id]

    async def close_all(self) -> None:
        for uid in list(self._clients.keys()):
            await self.close_user(uid)

    async def _call(self, user_id: str, tool_name: str, arguments: dict) -> dict:
        try:
            url = f"{MCP_BASE_URL}/{self.client_name}/http/{user_id}"
            async with Client(url) as client:
                result = await client.call_tool(tool_name, arguments)
                text = result.content[0].text
                logger.info(f"MCP response raw ({tool_name}): {text[:200]}")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}
        except Exception as e:
            logger.error(f"MCP call {tool_name}({user_id}) failed: {e}")
            raise

    # ---- OpenMemory MCP 工具 ----

    async def add_memories(self, text: str, user_id: str, infer: bool = True) -> dict:
        """调用 add_memories(text, infer)"""
        return await self._call(user_id, "add_memories", {
            "text": text,
            "infer": infer,
        })

    async def search_memory(self, query: str, user_id: str) -> dict:
        """调用 search_memory(query)"""
        return await self._call(user_id, "search_memory", {"query": query})

    async def list_memories(self, user_id: str) -> dict:
        """调用 list_memories()"""
        return await self._call(user_id, "list_memories", {})

    async def delete_all_memories(self, user_id: str) -> dict:
        """调用 delete_all_memories()"""
        return await self._call(user_id, "delete_all_memories", {})


mcp_client = McpClient()
