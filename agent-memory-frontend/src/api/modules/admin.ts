import { request } from '@/api/request'
import type {
  AdminDashboardParams,
  AdminDashboardResult,
  AdminStatsResult,
} from '@/api/types'

export function getAdminStats() {
  return request<AdminStatsResult>({
    url: '/api/v1/admin/stats',
    method: 'GET',
  })
}

export function getAdminDashboard(params: AdminDashboardParams = {}) {
  const searchParams = new URLSearchParams({
    hours: String(params.hours ?? 24),
    trend_days: String(params.trendDays ?? 7),
  })

  return request<AdminDashboardResult>({
    url: `/api/v1/admin/dashboard?${searchParams.toString()}`,
    method: 'GET',
  })
}
