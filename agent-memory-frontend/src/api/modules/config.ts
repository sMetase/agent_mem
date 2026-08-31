import { request } from '@/api/request'

export interface LlmConfig {
  llm_model?: string | null
  has_api_key?: boolean
}

export interface LlmConfigUpdate {
  llm_model?: string
  llm_api_key?: string
}

export function getLlmConfig() {
  return request<LlmConfig>({ url: '/api/v1/config/llm', method: 'GET' })
}

export function updateLlmConfig(payload: LlmConfigUpdate) {
  return request<{ updated: boolean }>({ url: '/api/v1/config/llm', method: 'PUT', data: payload })
}
