import { useCallback } from 'react'
import { searchMemories } from '@/api/modules/memory'

export function useMemorySearch() {
  return useCallback(searchMemories, [])
}
