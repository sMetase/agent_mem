import type { AppConfig } from '@/api/types'

function asTrimmedString(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

export function normalizeBaseUrl(value: unknown) {
  return asTrimmedString(value).replace(/\/+$/, '')
}

export function normalizeAppConfig(config: Partial<AppConfig>): AppConfig {
  return {
    baseUrl: normalizeBaseUrl(config.baseUrl),
    userId: asTrimmedString(config.userId),
    sceneId: asTrimmedString(config.sceneId),
    agentId: asTrimmedString(config.agentId),
    apiKey: asTrimmedString(config.apiKey),
    sessionId: asTrimmedString(config.sessionId),
  }
}

export function validateRequiredAppConfig(config: AppConfig) {
  if (!normalizeBaseUrl(config.baseUrl)) return '请先配置后端 Base URL'
  if (!asTrimmedString(config.userId)) return '请先配置 User ID'
  if (!asTrimmedString(config.sceneId)) return '请先配置 Scene ID'
  return null
}
