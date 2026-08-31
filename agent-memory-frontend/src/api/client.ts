import axios from 'axios'
import { normalizeBaseUrl } from '@/utils/config'
import { getStoredAppConfig } from '@/utils/storage'

export const defaultBaseUrl =
  normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL) || 'http://localhost:8000'

const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS)
export const apiTimeout =
  Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 10000

export const apiClient = axios.create({
  baseURL: defaultBaseUrl,
  timeout: apiTimeout,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const appConfig = getStoredAppConfig()

  config.baseURL = normalizeBaseUrl(appConfig.baseUrl) || defaultBaseUrl

  // 主链路鉴权约定：从第 3 步起，每个请求都携带三个 Header。
  const applyHeader = (name: string, value: string) => {
    if (value) {
      config.headers.set(name, value)
    } else {
      config.headers.delete(name)
    }
  }

  applyHeader('X-API-Key', appConfig.apiKey)
  applyHeader('X-User-Id', appConfig.userId)
  applyHeader('X-Agent-Id', appConfig.agentId)

  return config
})
