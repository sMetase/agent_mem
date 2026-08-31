import { useCallback } from 'react'
import { getTaskProgress } from '@/api/modules/task'

export function useTaskProgress() {
  return useCallback(getTaskProgress, [])
}
