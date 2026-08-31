# C Management Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build C direction management functionality for Memory, Task, and Settings pages while preserving the existing React/Vite/TypeScript project shell and A/B team boundaries.

**Architecture:** Keep API access in `src/api/modules/*`, configuration in `useAppStore`, and page-level orchestration inside `src/pages/Memory`, `src/pages/Task`, and `src/pages/Settings`. Extend existing business components (`MemoryCard`, `MemoryFilterBar`, `TaskProgressPanel`, `ConfigForm`) instead of duplicating UI.

**Tech Stack:** React 19, Vite 8, TypeScript 6, Ant Design 5, Axios, Zustand, React Router 7, oxlint.

## Global Constraints

- Work on branch `feature/memory-task`, targeting PRs into `dev`, not `main`.
- Do not rebuild `src/router`, `src/layouts`, sidebar, global layout, or chat flow.
- Do not introduce raw axios calls in pages; use `src/api/request.ts` and `src/api/modules/*`.
- Do not bypass `useAppStore`/`src/utils/storage.ts` for local integration config.
- Keep shared API/type/store changes narrow and compatible with A and B directions.
- Memory management is priority 1, task management priority 2, settings/config stability priority 3.
- Destructive memory actions require confirmation, especially delete-all.

---

## Current Structure Review

### Existing Foundations To Preserve

- `src/router/route-config.tsx` already registers Chat, Memory, Task, and Settings.
- `src/layouts/*` already provides the app shell and sidebar navigation.
- `src/components/common/*` already provides page containers, sections, feedback states, dialogs, status tags, and error boundaries.
- `src/api/client.ts` already reads persisted app config before each request and injects `baseUrl` plus optional `X-API-Key`.
- `src/api/modules/memory.ts` already exposes `listMemories`, `updateMemory`, `deleteMemory`, and `deleteAllMemories`.
- `src/api/modules/task.ts` already exposes `createTask`, `getTaskProgress`, and `updateTaskProgress`.
- `src/store/appStore.ts` and `src/utils/storage.ts` are the correct config path for `baseUrl`, `userId`, `sceneId`, `agentId`, and `apiKey`.

### Gaps In C-Owned Areas

- `src/pages/Memory/index.tsx` still uses `mockMemories` and local mock filtering only.
- `src/pages/Task/index.tsx` still uses `mockTaskProgress` and placeholder buttons.
- `src/pages/Settings/index.tsx` saves config but has no required-field validation surfaced to dependent pages.
- `src/components/business/MemoryCard/index.tsx` displays only basic provenance and has no edit/delete actions.
- `src/components/business/MemoryFilterBar/index.tsx` supports keyword/type but hardcodes garbled labels and does not expose refresh/clear-all actions.
- `src/components/business/TaskProgressPanel/index.tsx` displays only counts and has garbled labels.
- Several C-facing files contain mojibake Chinese strings. Fix C-owned files during implementation; coordinate separately before touching A-owned route/layout copy.

---

### Task 1: C-Owned Text And Shared Type Cleanup

**Files:**
- Modify: `src/api/types.ts`
- Modify: `src/constants/memory.ts`
- Modify: `src/components/business/MemoryFilterBar/index.tsx`
- Modify: `src/components/business/MemoryCard/index.tsx`
- Modify: `src/components/business/TaskProgressPanel/index.tsx`
- Modify: `src/components/business/ConfigForm/index.tsx`
- Modify: `src/pages/Memory/index.tsx`
- Modify: `src/pages/Task/index.tsx`
- Modify: `src/pages/Settings/index.tsx`

**Interfaces:**
- Produces: readable C-owned Chinese labels and aligned frontend types.
- Consumes: existing `MemoryItem`, `TaskCreatePayload`, `TaskInfo`, `TaskProgressResult`, `AppConfig`.

- [ ] Replace mojibake text in C-owned files with readable Chinese.
- [ ] Keep route/layout/common component mojibake out of scope unless a C page cannot function without the change.
- [ ] Add optional type fields only when backed by docs or UI needs:

```ts
export interface MemoryItem {
  memory_id: string
  content: string
  memory_type?: string
  scene_id?: string
  task_id?: string
  relevance_score?: number
  created_at?: string
  updated_at?: string
}

export interface TaskProgressUpdatePayload {
  status?: 'pending' | 'in_progress' | 'completed' | string
  progress?: string
  completed_items?: string[]
  pending_items?: string[]
}
```

- [ ] Update `updateTaskProgress` to consume `TaskProgressUpdatePayload` instead of `Record<string, unknown>`.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 2: Settings Validation As The Integration Gate

**Files:**
- Modify: `src/components/business/ConfigForm/index.tsx`
- Modify: `src/pages/Settings/index.tsx`
- Optional create: `src/utils/config.ts`

**Interfaces:**
- Produces: `validateRequiredAppConfig(config: AppConfig): string | null` if reused by Memory/Task.
- Consumes: `useAppStore((state) => state.config)` and `setConfig`.

- [ ] Add Ant Design form rules for required `baseUrl`, `userId`, and `sceneId`.
- [ ] Keep `agentId` and `apiKey` editable but optional for current dev auth.
- [ ] Trim string fields before saving:

```ts
const normalizedValues: AppConfig = {
  baseUrl: values.baseUrl.trim(),
  userId: values.userId.trim(),
  sceneId: values.sceneId.trim(),
  agentId: values.agentId.trim(),
  apiKey: values.apiKey.trim(),
}
```

- [ ] If Memory/Task need preflight validation, create `src/utils/config.ts` with:

```ts
import type { AppConfig } from '@/api/types'

export function validateRequiredAppConfig(config: AppConfig) {
  if (!config.baseUrl.trim()) return '请先配置后端 Base URL'
  if (!config.userId.trim()) return '请先配置 User ID'
  if (!config.sceneId.trim()) return '请先配置 Scene ID'
  return null
}
```

- [ ] Use existing `showSuccessMessage` for successful save.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 3: Memory List Loading And Local Filtering

**Files:**
- Modify: `src/pages/Memory/index.tsx`
- Modify: `src/store/memoryStore.ts` only if page cache should remain shared.
- Modify: `src/components/business/MemoryFilterBar/index.tsx`
- Modify: `src/components/business/MemoryCard/index.tsx`

**Interfaces:**
- Consumes: `listMemories(userId: string): Promise<MemoryItem[]>`.
- Produces: real Memory page loading/error/empty/list states.

- [ ] Replace `mockMemories` with `listMemories(config.userId)` in a page-level `loadMemories` callback.
- [ ] Guard loading with `validateRequiredAppConfig(config)` before API calls.
- [ ] Store loaded data in page state or `useMemoryStore`; prefer page state unless another page needs the list immediately.
- [ ] Keep keyword and memory type filtering local because `/memory/list` docs only define `user_id`.
- [ ] Clearly isolate local filtering:

```ts
const filteredMemories = useMemo(() => {
  const normalizedKeyword = keyword.trim().toLowerCase()
  return memories.filter((item) => {
    const matchKeyword =
      !normalizedKeyword || item.content.toLowerCase().includes(normalizedKeyword)
    const matchType = type === 'all' || item.memory_type === type
    return matchKeyword && matchType
  })
}, [keyword, memories, type])
```

- [ ] Preserve provenance in `MemoryCard`: `memory_type`, `scene_id`, `task_id`, `created_at`, `relevance_score`, and `memory_id`.
- [ ] Add refresh action near filter controls.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 4: Memory Edit And Single Delete Flows

**Files:**
- Modify: `src/pages/Memory/index.tsx`
- Modify: `src/components/business/MemoryCard/index.tsx`
- Optional modify: `src/components/common/ConfirmDialog/index.tsx`

**Interfaces:**
- Consumes: `updateMemory(memoryId: string, content: string)`.
- Consumes: `deleteMemory(memoryId: string, reason?: string)`.
- Produces: editable memory card actions with confirmation and user feedback.

- [ ] Extend `MemoryCard` props:

```ts
interface MemoryCardProps {
  memory: MemoryItem
  onEdit?: (memory: MemoryItem) => void
  onDelete?: (memory: MemoryItem) => void
  actionLoading?: boolean
}
```

- [ ] Add Edit and Delete actions to the card without changing its responsibility to data fetching.
- [ ] Implement edit modal/form in `MemoryPage` with required non-empty content validation.
- [ ] On save, call `updateMemory(memory.memory_id, content.trim())`, show success, then refresh the list.
- [ ] Implement delete confirmation with optional reason. If `ConfirmDialog` cannot accept input, use `Modal.confirm` plus a local `Input.TextArea` in Memory page.
- [ ] On delete, call `deleteMemory(memory.memory_id, reason.trim() || undefined)`, show success, then refresh the list.
- [ ] Disable repeated actions while a mutation is pending.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 5: Memory Clear-All Flow

**Files:**
- Modify: `src/pages/Memory/index.tsx`
- Modify: `src/components/business/MemoryFilterBar/index.tsx`

**Interfaces:**
- Consumes: `deleteAllMemories(userId: string)`.
- Produces: destructive clear-all action with strong confirmation.

- [ ] Add a clear-all button in the Memory page header or filter bar.
- [ ] Require strong confirmation text before clearing, for example `清空全部记忆`.
- [ ] Confirmation modal copy must include the current `userId` so the user sees the target scope.
- [ ] On confirm, call `deleteAllMemories(config.userId)`, show success, reset local filters, and reload.
- [ ] Use Ant Design `Button danger` and keep the action visually separate from normal refresh/filter controls.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 6: Task Creation And Progress Query

**Files:**
- Modify: `src/pages/Task/index.tsx`
- Modify: `src/components/business/TaskProgressPanel/index.tsx`
- Optional create: `src/pages/Task/components/TaskCreateForm.tsx`
- Optional create: `src/pages/Task/components/TaskQueryBar.tsx`

**Interfaces:**
- Consumes: `createTask(payload: TaskCreatePayload)`.
- Consumes: `getTaskProgress(taskId: string)`.
- Produces: task creation form, selected task id, progress refresh state.

- [ ] Replace `mockTaskProgress` with local state:

```ts
const [selectedTaskId, setSelectedTaskId] = useState('')
const [progress, setProgress] = useState<TaskProgressResult | null>(null)
const [loading, setLoading] = useState(false)
const [error, setError] = useState<unknown>(null)
```

- [ ] Add a task creation form with `title`, `goal`, `scene_id`, and `user_id`; default `scene_id` and `user_id` from `useAppStore`.
- [ ] Validate required `title`, `goal`, `user_id`, and `scene_id`.
- [ ] On create, call `createTask`, set `selectedTaskId` to returned `task_id`, show success, then call `getTaskProgress`.
- [ ] Add query/refresh controls for an entered `task_id`.
- [ ] Show loading/error/empty states using existing `FeedbackState`.
- [ ] Ensure `TaskProgressPanel` displays `task_id`, `status`, `completed_count`, `pending_count`, and `related_memory_count`.
- [ ] Run `pnpm lint` and `pnpm build`.

---

### Task 7: Optional Task Progress Update UI

**Files:**
- Modify: `src/pages/Task/index.tsx`
- Optional create: `src/pages/Task/components/TaskProgressUpdateForm.tsx`
- Modify: `src/api/modules/task.ts`
- Modify: `src/api/types.ts`

**Interfaces:**
- Consumes: `updateTaskProgress(taskId: string, payload: TaskProgressUpdatePayload)`.
- Produces: small manual progress update form.

- [ ] Add this task only after Task 6 is stable; it is useful but not required for first usable C delivery.
- [ ] Provide fields for `status`, `progress`, `completed_items`, and `pending_items`.
- [ ] Convert line-separated text areas into string arrays:

```ts
function linesToArray(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}
```

- [ ] Submit only non-empty fields to avoid overwriting backend state with blanks.
- [ ] Refresh `getTaskProgress(selectedTaskId)` after successful update.
- [ ] Run `pnpm lint` and `pnpm build`.

---

## Suggested PR Split

1. **PR 1: Settings + C text cleanup**
   - Config form validation, readable C-owned text, minimal type additions.
2. **PR 2: Memory read/filter/provenance**
   - Real `listMemories`, loading/error/empty states, provenance display, refresh.
3. **PR 3: Memory mutations**
   - Edit, delete, clear-all, confirmations, feedback.
4. **PR 4: Task create/query/progress**
   - Task form, progress query, refresh, optional progress update.

## Verification Checklist

- [ ] `pnpm lint`
- [ ] `pnpm build`
- [ ] Memory page with missing config shows a friendly configuration warning.
- [ ] Memory page with backend down shows `FeedbackState` error.
- [ ] Memory page with empty backend shows empty state.
- [ ] Memory list preserves `memory_id`, `memory_type`, `scene_id`, `task_id`, `created_at`, and `relevance_score` where present.
- [ ] Edit memory rejects blank content and refreshes after success.
- [ ] Delete memory asks for confirmation and optional reason.
- [ ] Clear all requires strong confirmation and displays the current `userId`.
- [ ] Task create uses configured `userId` and `sceneId` defaults.
- [ ] Task progress query works by returned or manually entered `task_id`.

## Collaboration Notes

- Coordinate with A direction before touching `src/router/route-config.tsx`, `src/layouts/*`, or common copy beyond C page requirements.
- Coordinate with B direction before changing `src/pages/Chat`, session lifecycle behavior, memory search/write hooks, or chat prompt assembly.
- Keep docs under `docs/` local-only unless the team explicitly wants them committed; this plan is intended as local implementation guidance.
