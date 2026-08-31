import type { MemoryItem } from '@/api/types'

export function buildPromptContext(memories: MemoryItem[]) {
  if (!memories.length) {
    return '（暂无历史记忆）'
  }

  return memories.map((item) => `- ${item.content}`).join('\n')
}
