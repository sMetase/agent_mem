import { create } from 'zustand'

interface TaskStoreState {
  activeTaskId: string
  setActiveTaskId: (taskId: string) => void
}

export const useTaskStore = create<TaskStoreState>((set) => ({
  activeTaskId: '',
  setActiveTaskId: (activeTaskId) => set({ activeTaskId }),
}))
