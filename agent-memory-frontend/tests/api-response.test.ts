import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/errors'
import { unwrapApiResponse } from '@/api/types'

describe('unwrapApiResponse', () => {
  it('returns data for a successful response', () => {
    expect(
      unwrapApiResponse<{ id: string }>({
        code: 0,
        message: 'success',
        data: { id: 'session_001' },
      }),
    ).toEqual({ id: 'session_001' })
  })

  it('preserves backend error metadata', () => {
    expect.assertions(4)

    try {
      unwrapApiResponse({
        code: 40001,
        message: 'user_id is required',
        data: null,
        error_code: 'INVALID_ARGUMENT',
        trace_id: 'trace_001',
      })
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect(error).toMatchObject({
        message: 'user_id is required',
        code: 40001,
        errorCode: 'INVALID_ARGUMENT',
        traceId: 'trace_001',
      })
      expect((error as ApiError).errorCode).toBe('INVALID_ARGUMENT')
      expect((error as ApiError).traceId).toBe('trace_001')
    }
  })

  it('rejects responses that do not follow the shared envelope', () => {
    expect(() => unwrapApiResponse({ success: true })).toThrow('接口响应格式不正确')
  })
})
