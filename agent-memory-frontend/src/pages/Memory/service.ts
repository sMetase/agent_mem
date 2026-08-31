import type { MemorySearchPayload } from '@/api/types'
import { buildMemoryTypeFilter } from '@/utils/memory'

interface MemorySearchFilterOptions {
  keyword: string
  memoryType: string
  userId: string
  rerank: boolean
  sessionId?: string
  taskId?: string
}

export function buildMemorySearchPayload({
  keyword,
  memoryType,
  userId,
  rerank,
  sessionId,
  taskId,
}: MemorySearchFilterOptions): MemorySearchPayload | null {
  const normalizedKeyword = keyword.trim()
  const normalizedMemoryType = memoryType.trim()
  const memoryTypes = buildMemoryTypeFilter(normalizedMemoryType)

  if (!normalizedKeyword && !memoryTypes) return null

  return {
    // search 接口要求保留 query 字段；纯类型筛选由记忆页先走完整列表，避免 Top-K 截断。
    query: normalizedKeyword,
    user_id: userId,
    memory_types: memoryTypes,
    session_id: sessionId?.trim() || undefined,
    task_id: taskId?.trim() || undefined,
    top_k: 50,
    rerank,
  }
}
