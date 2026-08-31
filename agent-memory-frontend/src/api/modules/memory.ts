import { request } from '@/api/request'
import type {
  MemoryContextPayload,
  MemoryContextResult,
  MemoryItem,
  MemoryListParams,
  MemoryListResult,
  MemoryProfileResult,
  MemoryStatsResult,
  MemorySearchPayload,
  MemorySearchResult,
  MemoryUpdatePayload,
  MemoryWritePayload,
  MemoryWriteResult,
} from '@/api/types'

export function getMemoryContext(payload: MemoryContextPayload) {
  return request<MemoryContextResult>({
    url: '/api/v1/memory/context',
    method: 'POST',
    data: payload,
  })
}

/** 用户画像报告（L3）：聚合 preference + fact 记忆生成 persona 文本。 */
export function getMemoryProfile(userId: string, maxMemories = 50) {
  return request<MemoryProfileResult>({
    url: '/api/v1/memory/profile',
    method: 'POST',
    data: {
      user_id: userId,
      max_memories: maxMemories,
    },
  })
}

export function searchMemories(payload: MemorySearchPayload) {
  return request<MemorySearchResult>({
    url: '/api/v1/memory/search',
    method: 'POST',
    data: payload,
  })
}

export function writeMemories(payload: MemoryWritePayload) {
  // write 已改异步：投递 Kafka 后毫秒级返回，用默认超时即可。
  return request<MemoryWriteResult>({
    url: '/api/v1/memory/write',
    method: 'POST',
    data: payload,
  })
}

export async function listMemories({
  userId,
  sceneId,
  taskId,
  sessionId,
  agentId,
  memoryType,
  timeStart,
  timeEnd,
  memoryScope,
  page = 1,
  pageSize = 20,
}: MemoryListParams) {
  const searchParams = new URLSearchParams({
    user_id: userId,
    page: String(page),
    page_size: String(pageSize),
  })
  if (sceneId) searchParams.set('scene_id', sceneId)
  if (taskId) searchParams.set('task_id', taskId)
  if (sessionId) searchParams.set('session_id', sessionId)
  if (agentId) searchParams.set('agent_id', agentId)
  if (memoryType) searchParams.set('memory_type', memoryType)
  if (timeStart) searchParams.set('time_start', timeStart)
  if (timeEnd) searchParams.set('time_end', timeEnd)
  if (memoryScope) searchParams.set('memory_scope', memoryScope)

  const result = await request<MemoryItem[] | MemoryListResult>({
    url: `/api/v1/memory/list?${searchParams.toString()}`,
    method: 'POST',
  })

  return Array.isArray(result)
    ? { items: result, total: result.length, page, page_size: pageSize }
    : result
}

export async function listAllMemories(
  params: Omit<MemoryListParams, 'page' | 'pageSize'> & { pageSize?: number },
) {
  const pageSize = Math.min(Math.max(params.pageSize ?? 100, 1), 100)
  const firstPage = await listMemories({ ...params, page: 1, pageSize })
  const effectivePageSize = firstPage.page_size || pageSize
  const pageCount = Math.ceil(firstPage.total / effectivePageSize)

  if (pageCount <= 1) return firstPage

  const remainingPages = await Promise.all(
    Array.from({ length: pageCount - 1 }, (_, index) => listMemories({
      ...params,
      page: index + 2,
      pageSize: effectivePageSize,
    })),
  )

  return {
    items: [firstPage, ...remainingPages].flatMap((page) => page.items),
    total: firstPage.total,
    page: 1,
    page_size: effectivePageSize,
  }
}

export function getMemoryStats(userId: string, sceneId?: string) {
  const searchParams = new URLSearchParams({ user_id: userId })
  if (sceneId) searchParams.set('scene_id', sceneId)

  return request<MemoryStatsResult>({
    url: `/api/v1/memory/stats?${searchParams.toString()}`,
    method: 'GET',
  })
}

export function updateMemory(payload: MemoryUpdatePayload) {
  return request<{ memory_id: string; updated: boolean; version?: number }>({
    url: '/api/v1/memory/update',
    method: 'PUT',
    data: payload,
  })
}

export async function deleteMemory(memoryId: string, reason?: string) {
  await request<{ memory_id: string; deleted: boolean; previous_status?: string }>({
    url: '/api/v1/memory/delete',
    method: 'DELETE',
    data: {
      memory_id: memoryId,
      reason,
    },
  })
}

export function deleteAllMemories(userId: string) {
  return request<string>({
    url: `/api/v1/memory/delete-all?user_id=${encodeURIComponent(userId)}`,
    method: 'POST',
  })
}
