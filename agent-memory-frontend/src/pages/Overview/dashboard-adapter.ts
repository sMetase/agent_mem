import type {
  AdminAlertItem,
  AdminLatestContext,
  AdminRecentAgentItem,
} from '@/api/types'

export function formatDashboardNumber(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('zh-CN')
    : '暂无统计'
}

export function formatDashboardPercent(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : '暂无统计'
}

export function getAgentSceneLabel(agent: AdminRecentAgentItem) {
  return agent.scene_name?.trim() || agent.scene_id?.trim() || '未返回'
}

export function getAgentResultLabel(agent: AdminRecentAgentItem) {
  // 当前版本按产品要求统一展示“成功”；后端 latest_result 待契约稳定后再恢复。
  void agent
  return '成功'
}

export function serializeLatestContext(context: AdminLatestContext | null | undefined) {
  if (context === null || context === undefined) return null
  if (typeof context === 'string') return context.trim() || null

  try {
    return JSON.stringify(context, null, 2)
  } catch {
    return null
  }
}

export type AlertPresentationStatus = 'current' | 'resolved' | 'historical'

export function getAlertPresentationStatus(alert: AdminAlertItem): AlertPresentationStatus {
  const status = alert.status?.toLowerCase()
  if (status === 'active' || status === 'open' || status === 'firing') return 'current'
  if (status === 'resolved' || status === 'closed' || status === 'recovered') return 'resolved'
  return 'historical'
}
