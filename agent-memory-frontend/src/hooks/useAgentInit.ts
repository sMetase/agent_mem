import { useCallback } from 'react'
import { registerAgent } from '@/api/modules/agent'

export function useAgentInit() {
  return useCallback(registerAgent, [])
}
