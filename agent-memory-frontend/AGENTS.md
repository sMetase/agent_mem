# Project Notes

## Workspace Shape

This workspace is now a React + Vite + TypeScript frontend repository for the intelligent agent memory management system.

The local checkout is aligned with GitHub repository `TaterMouse/agent-memory-frontend`. The active work for this agent is C direction management functionality on branch `feature/memory-task`, based on `dev`.

The planning materials live under `docs/` and define the intended frontend scope, API contract, feature hierarchy, prototype feedback, mem0 feasibility notes, and collaboration split. `docs/` and `AGENTS.md` are intentionally ignored by git and should stay local-only reference files.

## Current Assignment

This agent is responsible for C direction: management functionality.

Primary scope:

1. Memory management page: `src/pages/Memory`
2. Task tracking page: `src/pages/Task`
3. Settings/configuration page: `src/pages/Settings`
4. Supporting state, API integration, and reusable business components only when they are needed by the C direction pages.

## Current Project Structure

The latest `dev` branch already contains the shared project shell from A direction:

- `src/router`: route metadata and page registration. Current entries are Chat, Memory, Task, and Settings.
- `src/layouts`: app shell and sidebar navigation.
- `src/components/common`: shared page containers, sections, loading/empty/error feedback, status tags, and error boundaries.
- `src/api`: axios client, request wrapper, API response unwrapping, shared types, and modules for agent/session/memory/task.
- `src/store`: Zustand stores for app config, memory cache, and session state.
- `src/utils`: storage, feedback, formatting, prompt, and error helpers.
- `src/mock`: temporary mock data used by unfinished pages.

C direction must build on this structure instead of replacing it.

## C Direction Work Scope

Memory management is the first priority.

- Replace `src/pages/Memory/index.tsx` mock-only rendering with real data loading from `listMemories`.
- Use app config from `useAppStore` for `userId`, `sceneId`, API base URL, and future API key behavior.
- Support keyword and memory type filtering. Prefer backend filters if the API supports them; otherwise keep local filtering clearly separated.
- Add edit flow through `updateMemory`, with validation and user feedback.
- Add single delete flow through `deleteMemory`, including confirmation and optional reason.
- Add clear-all flow through `deleteAllMemories`, with strong confirmation because it is destructive.
- Preserve provenance fields in the UI where present: memory type, scene, task, created time, relevance score, and memory id.
- Keep `MemoryCard` and `MemoryFilterBar` as C-owned business components and extend them rather than duplicating similar UI.

Task management is the second priority.

- Replace `src/pages/Task/index.tsx` mock progress display with real task create and progress query flows.
- Use `createTask`, `getTaskProgress`, and `updateTaskProgress` from `src/api/modules/task.ts`.
- Provide a clear task creation form for title, goal, scene id, and user id.
- Provide refresh/query behavior for a selected or entered `task_id`.
- Show task status, completed count, pending count, and related memory count through `TaskProgressPanel`.
- If additional task detail fields are needed, extend shared API types carefully and keep payload shape aligned with backend docs.

Settings/configuration is the third priority but must remain stable because other pages depend on it.

- Keep `src/pages/Settings/index.tsx` responsible for local integration configuration.
- Keep `ConfigForm` focused on editable config fields such as base URL, user id, scene id, agent id, and API key.
- Store config through `useAppStore` and `src/utils/storage.ts`; do not bypass the store with scattered localStorage calls.
- Add validation for required fields before pages perform API calls.
- If adding agent registration or scene creation controls, keep them clearly separated from the basic config form and reuse existing API modules where possible.

## C Direction Non-Goals

- Do not rebuild the router, app shell, sidebar, or global layout for C pages.
- Do not take ownership of `src/pages/Chat`, chat message flow, session lifecycle UI, or AI reply generation.
- Do not rewrite `src/api/client.ts` or `src/api/request.ts` unless the backend contract forces a small shared fix.
- Do not introduce a second request layer or call raw `axios` directly from pages.
- Do not replace Zustand stores with another state library.
- Do not move C page state into global store unless it is shared across pages or needed for integration.
- Do not remove tracked team docs such as `docs/collaboration.md`; note that local planning docs under `docs/` may be ignored by `.gitignore`, but already tracked files remain part of the repo.

## Expected C Direction Deliverables

- Memory page can list, filter, edit, delete, and clear memories against the configured backend or gracefully show loading/error/empty states.
- Task page can create or inspect a task and refresh progress against the configured backend or gracefully show loading/error/empty states.
- Settings page can reliably save local integration config used by API requests.
- C-owned business components remain reusable, readable, and aligned with Ant Design and existing common components.
- Any shared API/type/store changes are minimal, justified, and called out in the final response or PR description.

Important collaboration boundary:

- Align with the team `dev` branch and the existing project skeleton before making changes.
- Do not overwrite or redesign A direction framework work in `src/layouts`, `src/router`, `src/store`, or `src/components/common` unless the C pages genuinely require a small compatible change.
- Do not take over B direction chat flow work in `src/pages/Chat`, session flow, or message interaction unless a small shared API/store adjustment is needed for integration.
- Keep shared changes narrow, documented in the final response, and compatible with the existing React Router, Axios, Zustand, and Ant Design stack.
- Work should be prepared for PRs into `dev`, not directly into `main`.

## Product Summary

The system stores valuable memory from user and AI conversations, then retrieves relevant memories before future replies so an agent can provide continuous and personalized responses.

Core loop:

1. User sends a message.
2. Frontend retrieves relevant memories.
3. AI response is generated with memory context.
4. Frontend writes the new conversation turn back to the memory system.

## Important Docs

- `docs/API接口文档-前端对接.md`: concise frontend-facing API guide and recommended integration flow.
- `docs/前端接口说明.md`: fuller API reference, response format, request examples, error codes, and frontend handling snippets.
- `docs/功能清单.md`: product feature hierarchy from access/write, modeling, retrieval, context assembly, management, security, and operations.
- `docs/mem0部署与测试报告.md`: local mem0 deployment notes, reusable capabilities, known gaps, and likely extension areas.
- `docs/原型页面意见汇总.md`: prototype feedback, including chart hover details and memory data-structure alignment concerns.
- `docs/面向大模型智能体的记忆系统功能设计文档*.docx`: larger design documents for deeper requirements.

## API Basics

- Base URL: `http://<后端IP>:8000`
- Data format: JSON
- Dev auth: currently no auth; future calls use `X-API-Key`.
- Standard success: `{ "code": 0, "message": "ok", "data": ... }`
- Standard failure: `{ "code": -1, "message": "...", "error_code": "...", "trace_id": "..." }`

Primary endpoints:

- `POST /api/v1/agent/register`
- `POST /api/v1/session`
- `POST /api/v1/session/{session_id}/close`
- `POST /api/v1/memory/search`
- `POST /api/v1/memory/write`
- `POST /api/v1/memory/list?user_id=...`
- `PUT /api/v1/memory/update`
- `DELETE /api/v1/memory/delete`
- `POST /api/v1/memory/delete-all?user_id=...`
- `POST /api/v1/memory/context`
- Optional task APIs under `/api/v1/task`
- Optional scene API: `POST /api/v1/scene`

## Frontend Implementation Priorities

When an app is created, prioritize these user-facing flows:

1. Agent registration and local API key handling.
2. Session creation and closing.
3. Chat flow with memory search before generation and memory write after each turn.
4. Memory management page: list, filter/group, edit, delete, clear all with confirmation.
5. Prompt/context preview using either search results or `/memory/context`.
6. Optional task tracking for long-running work.

## Design And Product Notes

- The frontend should expose memory provenance: type, scene, task, created time, relevance score, and update/delete status where available.
- Memory types in current docs include `preference`, `fact`, `task`, `decision`, and `constraint`.
- Write events include `ADD`, `SKIP`, and `MERGE`; UI feedback should treat `SKIP` quietly.
- Error handling should allow graceful degradation: if memory search fails, the chat can continue without injected memory.
- Prototype feedback calls out the overview trend chart: add hover detail for time buckets.
- Prototype feedback also flags that mock memory data structures should be aligned with the backend memory unit schema before formal development.

## Local Backend Context

The mem0 report says local deployment used Docker Compose with PostgreSQL + pgvector, Neo4j, and Ollama. `infer=false` write/search/update/delete paths worked in tests; `infer=true` automatic extraction with the local model returned empty results and likely needs extension or prompt/model work.

## Development Conventions

- Preserve existing Chinese documentation style unless asked otherwise.
- Prefer creating a standard frontend scaffold only after the user chooses or confirms the stack.
- If building the frontend from scratch, React + TypeScript + Vite is a reasonable fit for a dashboard/admin-style tool unless project constraints say otherwise.
- Keep API integration isolated in a client/service layer so endpoint details and future `X-API-Key` auth can change cleanly.
- Add confirmation UI for destructive memory actions, especially delete-all.
