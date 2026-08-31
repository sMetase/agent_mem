import { create } from 'zustand'
import type { AppConfig } from '@/api/types'
import { getStoredAppConfig, saveAppConfig } from '@/utils/storage'

interface AppStoreState {
  config: AppConfig
  setConfig: (config: AppConfig) => void
}

export const useAppStore = create<AppStoreState>((set) => ({
  config: getStoredAppConfig(),
  setConfig: (config) => {
    saveAppConfig(config)
    set({ config })
  },
}))
