# -*- coding: utf-8 -*-
"""
语言自动检测单元测试 — 纯逻辑，无需 DB / LLM。

覆盖 detect_language 的中英判定（含 l1_worker 拼出的 `[record_id] [role]: ...`
前缀格式）与 language_instruction 的注入行为。
"""

import pytest

from app.services.language_detect import detect_language, language_instruction


# ============================================================
# detect_language
# ============================================================

def test_detect_pure_chinese():
    assert detect_language("你好，今天天气不错，我们下午开会讨论方案。") == "zh"


def test_detect_pure_english():
    assert detect_language("Hello, we need to finalize the migration plan by Friday.") == "en"


def test_detect_l1_worker_chinese_prefix():
    # l1_worker 拼的 text 带 [record_id] [role]: 前缀，中文内容仍应判 zh
    text = "[7f3a] [user]: 帮我安排一下下周的会议\n[9b2c] [assistant]: 好的，已安排周三上午十点"
    assert detect_language(text) == "zh"


def test_detect_l1_worker_english_prefix():
    text = "[7f3a] [user]: Let me know when the report is ready\n[9b2c] [assistant]: Sure, will do"
    assert detect_language(text) == "en"


def test_detect_empty_and_unknown():
    assert detect_language("") == "unknown"
    assert detect_language("   ") == "unknown"
    # 只有数字/符号，无可判字符
    assert detect_language("12345 67890 !!!") == "unknown"


def test_detect_mixed_falls_to_unknown():
    # 中英占比接近 → unknown（保持原静态规则，不注入）
    mixed = "中文 English 混用 mixed content 测试 test"
    assert detect_language(mixed) == "unknown"


# ============================================================
# language_instruction
# ============================================================

def test_instruction_for_zh_and_en():
    zh = language_instruction("zh")
    assert zh != ""
    assert "中文" in zh

    en = language_instruction("en")
    assert en != ""
    assert "English" in en


def test_instruction_empty_for_unknown_none_and_unsupported():
    assert language_instruction(None) == ""
    assert language_instruction("unknown") == ""
    assert language_instruction("ja") == ""


def test_instruction_append_keeps_base_prompt_intact():
    base = "你是一个记忆抽取系统。"
    injected = base + language_instruction("en")
    assert injected.startswith(base)
    assert "Output Language" in injected


def test_instruction_empty_append_is_noop():
    base = "你是一个记忆抽取系统。"
    assert base + language_instruction(None) == base


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
