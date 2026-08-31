import { describe, expect, it } from 'vitest'
import { buildAdminApiLogsUrl, buildAdminRetrievalLogsUrl } from '@/api/modules/monitoring'
import type { AdminApiLogItem } from '@/api/types'
import {
  filterFailedApiLogs,
  getMonitoringMode,
  getResponseCodeColor,
  truncateLogText,
} from '@/pages/Monitoring/model'

function apiLog(overrides: Partial<AdminApiLogItem>): AdminApiLogItem {
  return {
    log_id: 'log_001',
    api_path: '/health',
    method: 'GET',
    response_code: 200,
    created_at: '2026-07-19T00:00:00Z',
    ...overrides,
  }
}

describe('monitoring routes', () => {
  it('selects the correct real-data panel from the current path', () => {
    expect(getMonitoringMode('/monitoring')).toBe('all')
    expect(getMonitoringMode('/monitoring/health')).toBe('health')
    expect(getMonitoringMode('/monitoring/calls')).toBe('calls')
    expect(getMonitoringMode('/monitoring/records')).toBe('records')
  })
})

describe('monitoring API queries', () => {
  it('builds encoded API log filters and pagination', () => {
    expect(buildAdminApiLogsUrl({
      apiPath: ' /api/v1/memory/search ',
      errorCode: ' INTERNAL ERROR ',
      hours: 168,
      page: 2,
      pageSize: 50,
    })).toBe('/api/v1/admin/api-logs?hours=168&page=2&page_size=50&api_path=%2Fapi%2Fv1%2Fmemory%2Fsearch&error_code=INTERNAL+ERROR')
  })

  it('builds retrieval log filters with safe defaults', () => {
    expect(buildAdminRetrievalLogsUrl({ agentId: ' agent_001 ' }))
      .toBe('/api/v1/admin/retrieval-logs?hours=24&page=1&page_size=20&agent_id=agent_001')
  })
})

describe('monitoring log adapters', () => {
  it('keeps only real failed calls and respects the visible limit', () => {
    const logs = [
      apiLog({ log_id: 'ok', response_code: 200 }),
      apiLog({ log_id: 'bad-request', response_code: 400 }),
      apiLog({ log_id: 'business-error', response_code: 200, error_code: 'FAILED' }),
      apiLog({ log_id: 'server-error', response_code: 500 }),
    ]

    expect(filterFailedApiLogs(logs, 2).map((log) => log.log_id))
      .toEqual(['bad-request', 'business-error'])
  })

  it('maps response codes and truncates sensitive query text', () => {
    expect(getResponseCodeColor(200)).toBe('green')
    expect(getResponseCodeColor(404)).toBe('orange')
    expect(getResponseCodeColor(503)).toBe('red')
    expect(truncateLogText('123456', 5)).toBe('12345…')
    expect(truncateLogText(null)).toBe('-')
  })
})
