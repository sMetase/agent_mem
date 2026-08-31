import type { AdminApiLogItem } from '@/api/types'

export type MonitoringMode = 'all' | 'health' | 'calls' | 'records'

export function getMonitoringMode(pathname: string): MonitoringMode {
  if (pathname.endsWith('/health')) return 'health'
  if (pathname.endsWith('/calls')) return 'calls'
  if (pathname.endsWith('/records')) return 'records'
  return 'all'
}

export function isFailedApiLog(log: AdminApiLogItem) {
  return log.response_code >= 400 || Boolean(log.error_code)
}

export function filterFailedApiLogs(logs: AdminApiLogItem[], limit = 10) {
  return logs.filter(isFailedApiLog).slice(0, limit)
}

export function getResponseCodeColor(responseCode: number) {
  if (responseCode >= 500) return 'red'
  if (responseCode >= 400) return 'orange'
  if (responseCode >= 300) return 'blue'
  return 'green'
}

export function truncateLogText(value: string | null | undefined, maxLength = 80) {
  if (!value) return '-'
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value
}
