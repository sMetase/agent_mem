# -*- coding: utf-8 -*-
"""
对话语言自动检测 — 供记忆抽取/生成阶段动态约束输出语言。

对齐 OpenViking 的 `_detect_language` + "All memory content MUST be written
in {output_language}" 模式：根据对话文本的 CJK / 拉丁字符占比判定语言，
生成一条注入到 system prompt 的输出语言指令，解决"中文 prompt 抽英文数据"
时自由文本字段（content / summary / description 等）语言漂移的问题。

本模块为纯标准库实现，不依赖 app 内任何组件，可直接单元测试。
"""

from __future__ import annotations

from typing import Optional

# CJK 相关字符区间（Unicode）：统一表意文字 + 扩展区 + 兼容表意文字 +
# 部首/笔画/符号/全角形式，足够把中文与拉丁文本区分开。
_CJK_RANGES = (
    (0x2E80, 0x2EFF),    # CJK Radicals Supplement
    (0x3000, 0x303F),    # CJK Symbols and Punctuation
    (0x31C0, 0x31EF),    # CJK Strokes
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0xFF00, 0xFFEF),    # Halfwidth and Fullwidth Forms（含全角标点）
    (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
)

# CJK 占比 ≥ 此值 → 判定为中文
_ZH_CJK_RATIO = 0.30
# CJK 占比 ≤ 此值 → 判定为英文（拉丁主导）
_EN_CJK_RATIO = 0.15


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in _CJK_RANGES)


def detect_language(text: str) -> str:
    """基于 CJK / 拉丁字符占比判定对话语言。

    Returns:
        "zh" / "en" / "unknown"。unknown 表示中英占比接近或没有可判字符，
        此时调用方应保持原有行为（不注入语言指令）。
    """
    if not text:
        return "unknown"

    cjk = 0
    latin = 0
    for ch in text:
        if ch.isspace():
            continue
        if _is_cjk(ch):
            cjk += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1

    total = cjk + latin
    if total == 0:
        return "unknown"

    cjk_ratio = cjk / total
    if cjk_ratio >= _ZH_CJK_RATIO:
        return "zh"
    if cjk_ratio <= _EN_CJK_RATIO:
        return "en"
    return "unknown"


# 输出语言指令块：按目标语言书写，给模型最强的语言信号。
_LANGUAGE_INSTRUCTIONS = {
    "zh": (
        "本对话为中文。所有自由文本字段（name、description、content、summary、"
        "key_points、tags、entities、conclusion、basis、item、preference_content、"
        "corrected_content 等）必须使用中文书写，保持 schema 定义的 JSON 字段名不变，"
        "不要混入英文。"
    ),
    "en": (
        "This conversation is in English. All free-text fields (name, description, "
        "content, summary, key_points, tags, entities, conclusion, basis, item, "
        "preference_content, corrected_content, etc.) MUST be written in English. "
        "Keep the JSON field names as defined in the schema; do not mix in other "
        "languages."
    ),
}


def language_instruction(output_language: Optional[str]) -> str:
    """返回追加到 system prompt 末尾的输出语言指令块。

    output_language 为 None / "unknown" / 未支持的语言时返回空串（不注入），
    调用方可直接 `EXTRACTION_SYSTEM_PROMPT + language_instruction(...)`。
    """
    if not output_language:
        return ""
    text = _LANGUAGE_INSTRUCTIONS.get(output_language)
    if not text:
        return ""
    return f"\n\n=== 输出语言要求 / Output Language ===\n{text}"
