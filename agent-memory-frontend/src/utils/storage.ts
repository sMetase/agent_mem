import type { AppConfig } from '@/api/types'
import { storageKeys } from '@/constants/storage'
import { normalizeAppConfig } from '@/utils/config'

const defaultConfig: AppConfig = {
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  userId: '',
  sceneId: '',
  agentId: '',
  apiKey: '',
  sessionId: '',
}

export function getStoredAppConfig(): AppConfig {
  const rawValue = localStorage.getItem(storageKeys.appConfig)
  if (!rawValue) {
    return defaultConfig
  }

  try {
    const parsedValue: unknown = JSON.parse(rawValue)
    if (typeof parsedValue !== 'object' || parsedValue === null) {
      return defaultConfig
    }

    return normalizeAppConfig({
      ...defaultConfig,
      ...parsedValue,
    })
  } catch {
    return defaultConfig
  }
}

export function saveAppConfig(config: AppConfig) {
  localStorage.setItem(storageKeys.appConfig, JSON.stringify(normalizeAppConfig(config)))
}
