# -*- coding: utf-8 -*-
"""
LLM Client — 直接调用 DeepSeek OpenAI 兼容 API（chat/completions）。

与 OpenMemory MCP Server 使用相同的 DeepSeek 配置，但提供自定义 prompt 的
结构化 JSON 抽取能力，绕过 mem0 的黑盒 infer 流程。
"""

import json
import os
import re
import asyncio
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.core.config import get_settings
from app.core.exceptions import LLMServiceError
from app.core.logger import get_logger

logger = get_logger("llm_client")

# DeepSeek 配置（优先从环境变量读取，与 OpenMemory MCP Server 一致）
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 2000
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds


class LLMClient:
    """DeepSeek chat-completion 客户端（OpenAI 兼容协议）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or DEEPSEEK_API_KEY
        self._base_url = (base_url or DEEPSEEK_BASE_URL).rstrip("/")
        self._model = model or DEEPSEEK_MODEL
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        response_format: Optional[dict] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """发送聊天请求，返回 assistant 的文本响应。model/api_key 可覆盖全局默认（agent 级配置）。"""
        model_name = model or self._model
        api_key_val = api_key or self._api_key
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key_val}"}

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.http.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(
                    f"LLM completion: model={model_name}, tokens={data.get('usage', {}).get('total_tokens', '?')}"
                )
                return content
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"LLM HTTP error (attempt {attempt}/{MAX_RETRIES}): {e.response.status_code}"
                )
                if attempt == MAX_RETRIES:
                    raise LLMServiceError(
                        f"DeepSeek API 返回错误 (status={e.response.status_code}): {e.response.text[:500]}"
                    )
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.warning(f"LLM request error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt == MAX_RETRIES:
                    raise LLMServiceError(f"DeepSeek API 请求失败: {str(e)}")
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        raise LLMServiceError("DeepSeek API 不可达，已达最大重试次数")

    async def extract_structured(
        self,
        system_prompt: str,
        user_content: str,
        output_schema: dict,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict:
        """
        发送带 system prompt 的结构化抽取请求，要求 JSON 输出。

        包含以下容错策略：
        1. 优先使用 JSON mode (response_format)
        2. LLM 返回后解析 JSON
        3. 解析失败则尝试 regex 提取 JSON 块
        4. 多次重试后仍失败则抛出 LLMServiceError
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        raw = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            model=model,
            api_key=api_key,
        )

        # 尝试直接解析
        try:
            result = json.loads(raw)
            logger.info("LLM structured extraction: JSON parsed successfully")
            return result
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON, attempting regex extraction")

        # Regex fallback: 提取第一个 JSON 对象或数组
        json_match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                logger.info("LLM structured extraction: JSON recovered via regex")
                return result
            except json.JSONDecodeError:
                pass

        raise LLMServiceError(
            f"DeepSeek 返回了无法解析的响应，原始内容前 500 字符: {raw[:500]}"
        )


# 模块级单例
llm_client = LLMClient()
