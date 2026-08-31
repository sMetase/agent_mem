import type { AdminApiLogItem } from '@/api/types'
import { isFailedApiLog } from '@/pages/Monitoring/model'

export type MonitorGranularity = 'hour' | 'day' | 'week'

/** 看板可选的时间窗口，配合粒度生成合适的桶数。 */
export const monitorGranularityOptions: Array<{ label: string; value: MonitorGranularity }> = [
  { label: '按小时', value: 'hour' },
  { label: '按天', value: 'day' },
  { label: '按周', value: 'week' },
]

/** 每种粒度对应的后端查询窗口（小时数）。 */
export const monitorGranularityHours: Record<MonitorGranularity, number> = {
  hour: 1,
  day: 24,
  week: 24 * 7,
}

/** 每种粒度期望展示的桶数量。 */
const granularityBucketCount: Record<MonitorGranularity, number> = {
  hour: 12,
  day: 7,
  week: 6,
}

export interface MonitorSeriesPoint {
  /** 桶的时间标签，例如 13:00、08-10、07-15 周 */
  time: string
  /** 该桶内接口调用次数 */
  count: number
  /** 该桶内接口调用成功率（0-1），无数据时为 null */
  rate: number | null
}

export interface MonitorSeries {
  granularity: MonitorGranularity
  points: MonitorSeriesPoint[]
  totalCalls: number
  failedCalls: number
  successRate: number | null
}

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const dayFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour12: false,
})

function formatDayBucket(date: Date) {
  return dayFormatter.format(date)
}

function formatWeekBucket(date: Date) {
  const monday = new Date(date)
  const day = monday.getDay() || 7
  monday.setDate(monday.getDate() - day + 1)
  return `周${'一二三四五六日'[(monday.getDay() + 6) % 7]} ${dayFormatter.format(monday)}`
}

/**
 * 将接口日志按时间桶聚合为频次与成功率序列。
 * 空日志时返回空序列，调用方展示空状态。
 */
export function buildMonitorSeries(logs: AdminApiLogItem[], granularity: MonitorGranularity, now = new Date()): MonitorSeries {
  const hours = monitorGranularityHours[granularity]
  const bucketCount = granularityBucketCount[granularity]

  const buckets: Array<{ label: string; start: number; end: number; count: number; failed: number }> = []

  for (let index = bucketCount - 1; index >= 0; index -= 1) {
    const end = now.getTime() - index * (hours / bucketCount) * 3600_000
    const start = now.getTime() - (index + 1) * (hours / bucketCount) * 3600_000
    const bucketDate = new Date(end)
    const label = granularity === 'hour'
      ? dateFormatter.format(bucketDate)
      : granularity === 'day'
        ? formatDayBucket(bucketDate)
        : formatWeekBucket(bucketDate)
    buckets.push({ label, start, end, count: 0, failed: 0 })
  }

  for (const log of logs) {
    const createdTime = log.created_at ? new Date(log.created_at).getTime() : Number.NaN
    if (!Number.isFinite(createdTime)) continue
    const bucket = buckets.find((item) => createdTime >= item.start && createdTime < item.end)
    if (!bucket) continue
    bucket.count += 1
    if (isFailedApiLog(log)) bucket.failed += 1
  }

  const totalCalls = buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  const failedCalls = buckets.reduce((sum, bucket) => sum + bucket.failed, 0)

  return {
    granularity,
    points: buckets.map((bucket) => ({
      time: bucket.label,
      count: bucket.count,
      rate: bucket.count === 0 ? null : (bucket.count - bucket.failed) / bucket.count,
    })),
    totalCalls,
    failedCalls,
    successRate: totalCalls === 0 ? null : (totalCalls - failedCalls) / totalCalls,
  }
}

/** 单条请求路径的调用统计 */
export interface ApiPathStat {
  path: string
  count: number
  failedCount: number
  successRate: number | null
  /** 最近一次耗时 */
  latestElapsedMs?: number | null
}

/**
 * 将接口日志按请求路径聚合，用于追溯各接口的健康状况。
 */
export function buildApiPathStats(logs: AdminApiLogItem[]): ApiPathStat[] {
  const pathMap = new Map<string, { count: number; failedCount: number; latestElapsedMs?: number | null }>()

  for (const log of logs) {
    const path = log.api_path || '(unknown)'
    const current = pathMap.get(path) ?? { count: 0, failedCount: 0 }
    current.count += 1
    if (isFailedApiLog(log)) current.failedCount += 1
    if (log.elapsed_ms != null) current.latestElapsedMs = log.elapsed_ms
    pathMap.set(path, current)
  }

  return Array.from(pathMap.entries())
    .map(([path, stat]) => ({
      path,
      count: stat.count,
      failedCount: stat.failedCount,
      successRate: stat.count === 0 ? null : (stat.count - stat.failedCount) / stat.count,
      latestElapsedMs: stat.latestElapsedMs,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
}

/** 失败调用追溯记录 */
export interface FailedCallTrace {
  path: string
  responseCode: number
  errorCode?: string | null
  traceId?: string | null
  elapsedMs?: number | null
  createdAt?: string | null
}

/**
 * 提取最近 N 条失败调用，用于失败追溯展示。
 */
export function buildFailedCallTraces(logs: AdminApiLogItem[], limit = 5): FailedCallTrace[] {
  return logs
    .filter(isFailedApiLog)
    .slice(0, limit)
    .map((log) => ({
      path: log.api_path || '(unknown)',
      responseCode: log.response_code,
      errorCode: log.error_code,
      traceId: log.trace_id,
      elapsedMs: log.elapsed_ms,
      createdAt: log.created_at,
    }))
}
