import { create } from 'zustand'
import type { MemoryItem } from '@/api/types'

interface MemoryStoreState {
  memories: MemoryItem[]
  setMemories: (memories: MemoryItem[]) => void
}

export const useMemoryStore = create<MemoryStoreState>((set) => ({
  memories: [],
  setMemories: (memories) => set({ memories }),
}))
