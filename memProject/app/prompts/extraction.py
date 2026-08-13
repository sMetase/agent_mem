# -*- coding: utf-8 -*-
"""
统一记忆抽取 Prompt — 单次 LLM 调用同时抽取五类信息，每条碎片独立评分。
"""

EXTRACTION_SYSTEM_PROMPT = """你是一个精确的记忆抽取系统。分析对话文本，从五个类别中抽取有价值的信息。对每个抽取的条目，根据它对未来对话的重要性，赋予一个价值分数（0.0-1.0）。

价值分数准则：
- 0.8-1.0: 对未来决策至关重要（截止时间、确认的计划、约束）
- 0.5-0.7: 明显有用（技术栈、偏好、任务进展）
- 0.3-0.5: 可能有价值（名称、背景上下文、过程细节）
- 0.1-0.2: 边缘价值（问候、闲聊、重复确认）

要抽取的类别：

1. 关键事实：
   - business_objects: 命名实体（人物、系统、项目、数据）。每条：name, type, description, value。
   - constraints: 规则、截止时间、限制。每条：type(technical/business/temporal/budget), description, scope, severity(high/medium/low), value。
   - confirmations: 明确同意的事项。每条：item, parties(list), context, value。

2. 任务状态：
   - current_progress: 任务当前进展（字符串）。包含 value。
   - completed_items: 已完成的交付物。每条：item, evidence, completion_note, value。
   - pending_items: 尚待完成的工作。每条：item, priority(high/medium/low), dependencies, value。

3. 用户偏好：
   - style_preferences: 沟通风格、语气、输出格式。每条：preference_object, preference_content, applicable_scenario, value。
   - habitual_preferences: 工作流、工具、流程习惯。每条：preference_object, preference_content, applicable_scenario, value。
   - decision_tendencies: 风险态度、权衡模式。每条：tendency_type(risk_attitude/priority_criteria/trade_off/evaluation), tendency_content, evidence, value。

4. 过程信息（含决策）：
   - execution_actions: 智能体动作（搜索、分析、计算、工具调用、生成、查询）。每条：action_name, action_type, input_summary, output_summary, tool_name, value。
   - intermediate_conclusions: 阶段性发现。每条：conclusion, basis, confidence(0-1), is_final(bool), value。
   - failure_records: 错误和恢复。每条：failure_point, failure_reason, attempted_recovery, was_resolved(bool), lesson_learned, value。
   - decisions: 选择的方法、策略。每条：type(plan/rationale/result), content, context, outcome(success/partial/failure/unknown), alternatives(list), value。

5. 反馈与纠正：
   - corrections: 用户对之前输出的纠正。每条：corrected_content, correction_instruction, original_context, correction_type(negation/revision/supplement), value。
   - confirmation_statuses: 用户确认/批准/拒绝。每条：confirmed_item, status(confirmed/rejected/partial/modified), parties_involved(list), context, value。
   - replacement_relationships: 新陈述替换旧陈述。每条：replaced_content, replacement_content, replacement_reason, scope(global/task_local/session_local), supersedes_memory_id, value。

只输出合法的 JSON。空类别使用空数组或空字符串。
对 value < 0.3 的条目，仍然包含在输出中——过滤会在下游完成。
"""

EXTRACTION_USER_TEMPLATE = """从以下对话文本中抽取有价值的信息。对每个条目，赋予一个价值分数（0.0-1.0）：

{text}"""

EXTRACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "key_facts": {
            "type": "object",
            "properties": {
                "business_objects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["name", "type", "description", "value"],
                    },
                },
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "description": {"type": "string"},
                            "scope": {"type": "string"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["type", "description", "severity", "value"],
                    },
                },
                "confirmations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "parties": {"type": "array", "items": {"type": "string"}},
                            "context": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["item", "context", "value"],
                    },
                },
            },
        },
        "task_state": {
            "type": "object",
            "properties": {
                "current_progress": {"type": "string"},
                "completed_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "evidence": {"type": "string"},
                            "completion_note": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["item", "value"],
                    },
                },
                "pending_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                            "dependencies": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["item", "priority", "value"],
                    },
                },
            },
        },
        "preferences": {
            "type": "object",
            "properties": {
                "style_preferences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "preference_object": {"type": "string"},
                            "preference_content": {"type": "string"},
                            "applicable_scenario": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["preference_object", "preference_content", "value"],
                    },
                },
                "habitual_preferences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "preference_object": {"type": "string"},
                            "preference_content": {"type": "string"},
                            "applicable_scenario": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["preference_object", "preference_content", "value"],
                    },
                },
                "decision_tendencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tendency_type": {"type": "string", "enum": ["risk_attitude", "priority_criteria", "trade_off", "evaluation"]},
                            "tendency_content": {"type": "string"},
                            "evidence": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["tendency_type", "tendency_content", "value"],
                    },
                },
            },
        },
        "process": {
            "type": "object",
            "properties": {
                "execution_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_name": {"type": "string"},
                            "action_type": {"type": "string", "enum": ["search", "analyze", "compute", "tool_call", "generate", "query"]},
                            "input_summary": {"type": "string"},
                            "output_summary": {"type": "string"},
                            "tool_name": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["action_name", "action_type", "value"],
                    },
                },
                "intermediate_conclusions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "conclusion": {"type": "string"},
                            "basis": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "is_final": {"type": "boolean"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["conclusion", "confidence", "is_final", "value"],
                    },
                },
                "failure_records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "failure_point": {"type": "string"},
                            "failure_reason": {"type": "string"},
                            "attempted_recovery": {"type": "string"},
                            "was_resolved": {"type": "boolean"},
                            "lesson_learned": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["failure_point", "failure_reason", "was_resolved", "value"],
                    },
                },
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["plan", "rationale", "result"]},
                            "content": {"type": "string"},
                            "context": {"type": "string"},
                            "outcome": {"type": "string", "enum": ["success", "partial", "failure", "unknown"]},
                            "alternatives": {"type": "array", "items": {"type": "string"}},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["type", "content", "value"],
                    },
                },
            },
        },
        "feedback": {
            "type": "object",
            "properties": {
                "corrections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "corrected_content": {"type": "string"},
                            "correction_instruction": {"type": "string"},
                            "original_context": {"type": "string"},
                            "correction_type": {"type": "string", "enum": ["negation", "revision", "supplement"]},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["corrected_content", "correction_instruction", "correction_type", "value"],
                    },
                },
                "confirmation_statuses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "confirmed_item": {"type": "string"},
                            "status": {"type": "string", "enum": ["confirmed", "rejected", "partial", "modified"]},
                            "parties_involved": {"type": "array", "items": {"type": "string"}},
                            "context": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["confirmed_item", "status", "value"],
                    },
                },
                "replacement_relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "replaced_content": {"type": "string"},
                            "replacement_content": {"type": "string"},
                            "replacement_reason": {"type": "string"},
                            "scope": {"type": "string", "enum": ["global", "task_local", "session_local"]},
                            "supersedes_memory_id": {"type": "string"},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["replaced_content", "replacement_content", "replacement_reason", "value"],
                    },
                },
            },
        },
    },
}
