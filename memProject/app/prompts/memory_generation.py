# -*- coding: utf-8 -*-
"""
记忆生成 Prompt — 将抽取结果转化为结构化记忆对象。
"""

MEMORY_GENERATION_SYSTEM_PROMPT = """You are a memory structuring system. Given extracted facts, task states, preferences, process information (including decisions), and feedback from a conversation, generate structured memory entries. Each memory should be a self-contained, useful piece of information for future retrieval.

For each distinct piece of information, produce:
- content: A natural, standalone memory sentence in the appropriate language (Chinese for Chinese content, English for English content). This is the primary retrievable text.
- summary: A concise 1-2 sentence summary of this memory.
- key_points: 2-5 bullet points capturing the essence (as a list of strings).
- memory_type: One of:
  - "fact": Objective facts, business objects, entities, constraints, deadlines
  - "preference": User preferences, habits, likes/dislikes, decision tendencies
  - "task_state": Task progress, status, pending items
  - "process": Workflows, procedures, methodologies, execution actions, decisions, lessons learned
  - "correction": User corrections, negations, revisions, or replacement of previous statements
- tags: 2-5 relevant tags for categorization and filtering.
- entities: Named entities (people, systems, projects, tools) referenced in this memory.
- importance: 0.0-1.0 float — how critical this information is for future decisions and context.
- confidence: 0.0-1.0 float — how certain/confirmed the information is based on the source text.

Guidelines:
- Group closely related facts into a single memory. Separate unrelated facts into different memories.
- Constraints (rules, limitations, deadlines) should be generated as "fact" type with high importance.
- For user preferences, generate ONE memory per distinct preference area (style, habit, decision tendency).
- For process information, focus on key decisions, reusable lessons and failure recovery patterns — not every action needs a memory.
- For feedback/corrections, prioritize replacement relationships and explicit negations over minor confirmations.
- Do NOT generate memories for trivial, conversational filler (greetings, small talk, etc.).
- For task state, create at most ONE memory summarizing the overall task status.
- If the extracted data is empty or contains only noise, return an empty memories array.
- Mark memories with low certainty (confidence < 0.5) — they should still be generated but with appropriately low confidence scores.
- Prioritize information that would be useful in future conversations.

Output ONLY valid JSON: {"memories": [...]}
"""

MEMORY_GENERATION_USER_TEMPLATE = """Generate structured memories from the following extraction results:

## Key Facts Extracted
Business Objects: {business_objects}
Constraints: {constraints}
Confirmations: {confirmations}

## Task State Extracted
Current Progress: {current_progress}
Completed Items: {completed_items}
Pending Items: {pending_items}

## User Preferences Extracted
Style Preferences: {style_preferences}
Habitual Preferences: {habitual_preferences}
Decision Tendencies: {decision_tendencies}

## Process Information Extracted (含历史决策)
Execution Actions: {execution_actions}
Intermediate Conclusions: {intermediate_conclusions}
Failure Records: {failure_records}
Decisions: {decisions}

## Feedback & Corrections Extracted
Corrections: {corrections}
Confirmation Statuses: {confirmation_statuses}
Replacement Relationships: {replacement_relationships}

Generate a list of structured memory entries from this data."""

MEMORY_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "memory_type": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "preference",
                            "task_state",
                            "process",
                            "correction",
                        ],
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": [
                    "content",
                    "summary",
                    "key_points",
                    "memory_type",
                    "tags",
                    "entities",
                    "importance",
                    "confidence",
                ],
            },
        }
    },
    "required": ["memories"],
}
