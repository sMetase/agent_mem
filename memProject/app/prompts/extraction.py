# -*- coding: utf-8 -*-
"""
统一记忆抽取 Prompt — 单次 LLM 调用同时抽取五类信息，每条碎片独立评分。
"""

EXTRACTION_SYSTEM_PROMPT = """You are a precise memory extraction system. Analyze the conversation text and extract valuable information across five categories. For each extracted item, assign a value score (0.0-1.0) based on how important it is for future conversations.

Value score guidelines:
- 0.8-1.0: Critical for future decisions (deadlines, confirmed plans, constraints)
- 0.5-0.7: Clearly useful (tech stacks, preferences, task progress)
- 0.3-0.5: Potentially useful (names, background context, process details)
- 0.1-0.2: Marginally useful (greetings, filler, repeated confirmations)

Categories to extract:

1. KEY FACTS:
   - business_objects: Named entities (people, systems, projects, data). Each: name, type, description, value.
   - constraints: Rules, deadlines, limitations. Each: type(technical/business/temporal/budget), description, scope, severity(high/medium/low), value.
   - confirmations: Items explicitly agreed upon. Each: item, parties(list), context, value.

2. TASK STATE:
   - current_progress: Where the task stands (string). Include a value.
   - completed_items: Finished deliverables. Each: item, evidence, completion_note, value.
   - pending_items: Work still to be done. Each: item, priority(high/medium/low), dependencies, value.

3. USER PREFERENCES:
   - style_preferences: Communication style, tone, output format. Each: preference_object, preference_content, applicable_scenario, value.
   - habitual_preferences: Workflow, tool, process habits. Each: preference_object, preference_content, applicable_scenario, value.
   - decision_tendencies: Risk attitude, trade-off patterns. Each: tendency_type(risk_attitude/priority_criteria/trade_off/evaluation), tendency_content, evidence, value.

4. PROCESS INFORMATION (including decisions):
   - execution_actions: Agent actions (search, analyze, compute, tool_call, generate, query). Each: action_name, action_type, input_summary, output_summary, tool_name, value.
   - intermediate_conclusions: Interim findings. Each: conclusion, basis, confidence(0-1), is_final(bool), value.
   - failure_records: Errors and recoveries. Each: failure_point, failure_reason, attempted_recovery, was_resolved(bool), lesson_learned, value.
   - decisions: Approaches, strategies chosen. Each: type(plan/rationale/result), content, context, outcome(success/partial/failure/unknown), alternatives(list), value.

5. FEEDBACK & CORRECTIONS:
   - corrections: User corrections of previous output. Each: corrected_content, correction_instruction, original_context, correction_type(negation/revision/supplement), value.
   - confirmation_statuses: User confirms/approves/rejects. Each: confirmed_item, status(confirmed/rejected/partial/modified), parties_involved(list), context, value.
   - replacement_relationships: New statement replaces old. Each: replaced_content, replacement_content, replacement_reason, scope(global/task_local/session_local), supersedes_memory_id, value.

Output ONLY valid JSON. Empty categories use empty arrays or empty strings.
For items with value < 0.3, still include them in the output — filtering will be done downstream.
"""

EXTRACTION_USER_TEMPLATE = """Extract valuable information from the following conversation text. For each item, assign a value score (0.0-1.0):

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
