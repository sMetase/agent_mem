import type { MemoryItem } from '@/api/types'

export function buildMemoryTypeFilter(memoryType?: string) {
  const normalizedMemoryType = memoryType?.trim()
  if (!normalizedMemoryType || normalizedMemoryType === 'all') return undefined

  // 后端历史数据使用 task_state，接口文档中仍保留 task；两者都纳入任务筛选。
  if (normalizedMemoryType === 'task' || normalizedMemoryType === 'task_state') {
    return ['task_state', 'task']
  }

  return [normalizedMemoryType]
}

export function filterMemoriesByType(memories: MemoryItem[], memoryTypes?: string[]) {
  if (!memoryTypes?.length) return memories

  const typeSet = new Set(memoryTypes)
  return memories.filter((memory) => typeSet.has(memory.memory_type ?? ''))
}
