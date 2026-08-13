# -*- coding: utf-8 -*-
"""
长对话压缩 Prompt — 语义压缩、关键保持、上下文补全。
"""

# ============================================================
# 5.4.1: 长对话语义压缩
# ============================================================

COMPRESSION_SYSTEM_PROMPT = """你是一个对话压缩系统。给定一段长对话历史，生成一个紧凑、结构化的摘要，保留未来任务续接所需的所有信息。

输出结构：
- conversation_overview: 1-3 句关于这次对话的高层概述
- key_facts: 稳定事实、实体、业务对象和已确认信息的列表
- user_preferences: 任何表达的偏好（风格、格式、方法、工具等）
- task_state: 当前任务进展、已完成项、待办项、生效约束
- key_decisions: 做出的决策，含理由和上下文
- corrections_and_feedback: 用户对智能体输出的纠正、否定或反馈
- important_context: 理解未来用户请求可能需要的上下文
- trivial_summary: 1 句话概括闲聊（可丢弃）

准则：
- 简洁但完整。每个事实 1-2 句话。
- 保留具体细节：名称、数字、日期、技术术语、约束。
- 用 [uncertain] 标记不确定的信息。
- 对纠正，始终注明从什么改成了什么（FROM → TO）。
- 如果某个部分没有内容，用空数组/空字符串。
- 语言与原始对话保持一致。

只输出合法的 JSON。"""

COMPRESSION_USER_TEMPLATE = """将以下对话历史压缩为结构化记忆：

{conversation_text}"""

COMPRESSION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "conversation_overview": {"type": "string"},
        "key_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "category": {"type": "string", "enum": ["entity", "constraint", "confirmation", "background", "result"]},
                    "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["fact", "category", "importance"],
            },
        },
        "user_preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "preference": {"type": "string"},
                    "category": {"type": "string", "enum": ["style", "format", "tool", "approach", "other"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["preference", "category", "confidence"],
            },
        },
        "task_state": {
            "type": "object",
            "properties": {
                "overall_progress": {"type": "string"},
                "completed_items": {"type": "array", "items": {"type": "string"}},
                "pending_items": {"type": "array", "items": {"type": "string"}},
                "active_constraints": {"type": "array", "items": {"type": "string"}},
                "current_phase": {"type": "string"},
            },
        },
        "key_decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "rationale": {"type": "string"},
                    "alternatives_considered": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["decision"],
            },
        },
        "corrections_and_feedback": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "corrected_from": {"type": "string"},
                    "corrected_to": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["corrected_from", "corrected_to"],
            },
        },
        "important_context": {"type": "array", "items": {"type": "string"}},
        "trivial_summary": {"type": "string"},
    },
    "required": [
        "conversation_overview", "key_facts", "user_preferences",
        "task_state", "key_decisions", "corrections_and_feedback",
        "important_context", "trivial_summary",
    ],
}


# ============================================================
# 5.4.2: 压缩后关键记忆保持验证
# ============================================================

PRESERVATION_CHECK_SYSTEM_PROMPT = """你是一个记忆保留审计器。比较原始对话片段与其压缩版本，识别压缩过程中丢失的任何关键信息。

检查：
1. 缺失的关键事实（实体、数字、日期、具体约束）
2. 缺失的用户偏好（风格、格式、方法偏好）
3. 缺失的任务状态（待办项、当前进展、阻碍）
4. 缺失的决策（确认的计划、理由）
5. 缺失的纠正（用户否定、修订）

对每个缺失项，指出：
- what_was_lost: 缺失的信息
- severity: "critical"（会导致未来任务出错）、"important"（有用的上下文丢失）、"minor"（锦上添花）
- suggested_fix: 如何把它加回压缩版本

只输出合法的 JSON。如果什么都没丢，返回空数组。"""

PRESERVATION_CHECK_USER_TEMPLATE = """原始对话（摘录）：
{original_text}

压缩版本：
{compressed_json}

检查丢失的关键信息。"""

PRESERVATION_CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "lost_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "what_was_lost": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critical", "important", "minor"]},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["what_was_lost", "severity"],
            },
        },
        "preservation_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["lost_items", "preservation_score"],
}


# ============================================================
# 5.4.3: 历史上下文补全
# ============================================================

CONTEXT_COMPLETION_SYSTEM_PROMPT = """你是一个上下文补全系统。给定当前用户查询和检索到的历史压缩记忆，构建智能体准确响应所需的完整上下文。

输出应该是一个自包含的 prompt 片段：
1. 总结相关用户偏好
2. 陈述相关关键事实
3. 描述当前任务状态
4. 注明适用的历史决策
5. 提及任何约束或纠正

使用清晰的章节标题。保持简洁——智能体的上下文窗口有限。
语言与查询保持一致。"""

CONTEXT_COMPLETION_USER_TEMPLATE = """当前查询: {query}

检索到的历史记忆：
{memories_text}

构建智能体响应当前查询所需的上下文。"""

CONTEXT_COMPLETION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "context_text": {"type": "string"},
        "sections_used": {"type": "array", "items": {"type": "string"}},
        "estimated_relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["context_text", "sections_used", "estimated_relevance"],
}
