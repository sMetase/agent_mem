import { request } from '@/api/request'

export interface LlmConfig {
  llm_model?: string | null
  has_api_key?: boolean
}

export interface LlmConfigUpdate {
  llm_model?: string
  llm_api_key?: string
}

export interface ExtractionSchedule {
  extraction_schedule_enabled: boolean
  extraction_window_start: string
  extraction_window_end: string
  extraction_timezone: string
}

export interface ExtractionScheduleUpdate {
  extraction_schedule_enabled?: boolean
  extraction_window_start?: string
  extraction_window_end?: string
  extraction_timezone?: string
}

export function getLlmConfig() {
  return request<LlmConfig>({ url: '/api/v1/config/llm', method: 'GET' })
}

export function updateLlmConfig(payload: LlmConfigUpdate) {
  return request<{ updated: boolean }>({ url: '/api/v1/config/llm', method: 'PUT', data: payload })
}

export function getExtractionSchedule() {
  return request<ExtractionSchedule>({ url: '/api/v1/config/extraction-schedule', method: 'GET' })
}

export function updateExtractionSchedule(payload: ExtractionScheduleUpdate) {
  return request<ExtractionSchedule>({
    url: '/api/v1/config/extraction-schedule',
    method: 'PUT',
    data: payload,
  })
}
