import { describe, expect, it } from 'vitest'
import { normalizeAppConfig, normalizeBaseUrl, validateRequiredAppConfig } from '@/utils/config'

describe('app config utilities', () => {
  it('normalizes values before they reach storage or requests', () => {
    expect(
      normalizeAppConfig({
        baseUrl: ' http://localhost:8000/// ',
        userId: ' user_001 ',
        sceneId: ' chat ',
        agentId: ' agent_001 ',
        apiKey: ' secret ',
        sessionId: ' sess_001 ',
      }),
    ).toEqual({
      baseUrl: 'http://localhost:8000',
      userId: 'user_001',
      sceneId: 'chat',
      agentId: 'agent_001',
      apiKey: 'secret',
      sessionId: 'sess_001',
    })
  })

  it('normalizes an empty base URL safely', () => {
    expect(normalizeBaseUrl(undefined)).toBe('')
  })

  it('reports the first missing required field', () => {
    expect(
      validateRequiredAppConfig({
        baseUrl: ' ',
        userId: 'user_001',
        sceneId: 'chat',
        agentId: '',
        apiKey: '',
        sessionId: '',
      }),
    ).toBe('请先配置后端 Base URL')
  })
})
