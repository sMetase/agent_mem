import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listMemories } from '@/api/modules/memory'
import { request } from '@/api/request'

vi.mock('@/api/request', () => ({
  request: vi.fn(),
}))

const requestMock = vi.mocked(request)

describe('listMemories', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  })

  it.each([
    { memoryScope: 'user' as const, expectedScope: 'user', expectedIdKey: null, expectedId: null },
    { memoryScope: 'session' as const, sessionId: 'session_001', expectedScope: 'session', expectedIdKey: 'session_id', expectedId: 'session_001' },
    { memoryScope: 'task' as const, taskId: 'task_001', expectedScope: 'task', expectedIdKey: 'task_id', expectedId: 'task_001' },
  ])('sends the selected memory layer to the backend', async ({ memoryScope, sessionId, taskId, expectedScope, expectedIdKey, expectedId }) => {
    await listMemories({
      userId: 'user_001',
      memoryScope,
      sessionId,
      taskId,
      page: 2,
      pageSize: 20,
    })

    const requestConfig = requestMock.mock.calls[0]?.[0]
    expect(requestConfig?.method).toBe('POST')
    const params = new URLSearchParams(requestConfig?.url?.split('?')[1])
    expect(params.get('user_id')).toBe('user_001')
    expect(params.get('memory_scope')).toBe(expectedScope)
    expect(expectedIdKey ? params.get(expectedIdKey) : params.has('session_id') || params.has('task_id')).toBe(expectedIdKey ? expectedId : false)
  })
})
