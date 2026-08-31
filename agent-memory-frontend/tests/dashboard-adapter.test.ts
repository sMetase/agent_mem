import { describe, expect, it } from 'vitest'
import {
  formatDashboardNumber,
  formatDashboardPercent,
  getAgentResultLabel,
  getAgentSceneLabel,
  getAlertPresentationStatus,
  serializeLatestContext,
} from '@/pages/Overview/dashboard-adapter'

describe('dashboard adapters', () => {
  it('uses explicit empty-state copy instead of claiming an unavailable endpoint', () => {
    expect(formatDashboardNumber(null)).toBe('暂无统计')
    expect(formatDashboardPercent(undefined)).toBe('暂无统计')
  })

  it('formats real dashboard values', () => {
    expect(formatDashboardNumber(6010)).toBe('6,010')
    expect(formatDashboardPercent(0.3757)).toBe('37.6%')
  })

  it('uses the requested success copy for agent write results', () => {
    const agent = { agent_id: 'agent_001', scene_id: null, scene_name: null, latest_result: null }
    expect(getAgentSceneLabel(agent)).toBe('未返回')
    expect(getAgentResultLabel(agent)).toBe('成功')
    expect(getAgentSceneLabel({ ...agent, scene_id: 'scene_a' })).toBe('scene_a')
  })

  it('supports a missing latest_context contract without rendering an error state', () => {
    expect(serializeLatestContext(undefined)).toBeNull()
    expect(serializeLatestContext('  ')).toBeNull()
    expect(serializeLatestContext({ memory_count: 2 })).toContain('"memory_count": 2')
  })

  it('distinguishes explicit current/resolved alerts from historical records', () => {
    expect(getAlertPresentationStatus({ message: 'x', status: 'active' })).toBe('current')
    expect(getAlertPresentationStatus({ message: 'x', status: 'resolved' })).toBe('resolved')
    expect(getAlertPresentationStatus({ message: 'x' })).toBe('historical')
  })
})
